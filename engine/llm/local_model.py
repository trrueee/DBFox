"""Sidecar ownership of a locally provisioned Ollama runtime."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from engine.agent.providers.openai import OpenAIModelAdapter
from engine.llm.config import LlmConfigurationError
from engine.llm.endpoint_policy import ResolvedLlmEndpoint
from engine.llm.http_clients import create_llm_async_http_client
from engine.local_execution.command import local_environment

if TYPE_CHECKING:
    from engine.local_execution.windows import WindowsProcess

LOCAL_MODEL_OUTPUT_TOKENS = 2_048
_LOOPBACK = "127.0.0.1"


class LocalModelProfile(BaseModel):
    """Private machine configuration written after a verified model pull."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*:[a-zA-Z0-9._-]+$", max_length=128)
    model_digest: str = Field(pattern=r"^(sha256:)?[a-f0-9]{64}$")
    model_size_bytes: int = Field(gt=0)
    executable: Path
    models_dir: Path
    state_dir: Path
    scratch_dir: Path
    context_length: int = Field(ge=8_192, le=32_768)


class ManagedLocalModel:
    def __init__(self, profile_path: Path) -> None:
        self.profile: LocalModelProfile | None = None
        self.configured = True
        try:
            profile = LocalModelProfile.model_validate_json(profile_path.read_text(encoding="utf-8-sig"))
            if (
                profile.executable.name.lower() != "ollama.exe"
                or profile.model_name.lower().endswith((":cloud", "-cloud"))
                or not all(
                    path.is_absolute() and not path.drive.startswith("\\\\")
                    for path in (profile.executable, profile.models_dir, profile.state_dir, profile.scratch_dir)
                )
            ):
                raise ValueError("Local model requires local absolute paths and a local model tag")
            self.profile = profile
        except FileNotFoundError:
            self.configured = False
        except (OSError, ValueError):
            # An invalid configured profile must never switch the user to cloud.
            pass
        self._lock = Lock()
        self._closed = False
        self._process: WindowsProcess | None = None
        self._endpoint: ResolvedLlmEndpoint | None = None
        self._drain_stop = Event()
        self._drainer: Thread | None = None

    def installation_error(self) -> str | None:
        profile = self.profile
        if not self.configured:
            return "LOCAL_MODEL_NOT_CONFIGURED"
        if profile is None:
            return "LOCAL_MODEL_PROFILE_INVALID"
        if os.name != "nt":
            return "LOCAL_MODEL_PLATFORM_UNSUPPORTED"
        try:
            if not profile.executable.is_file() or not all(
                path.is_dir() for path in (profile.models_dir, profile.state_dir, profile.scratch_dir)
            ):
                return "LOCAL_MODEL_FILES_MISSING"
        except OSError:
            return "LOCAL_MODEL_FILES_MISSING"
        return None

    def require_profile(self) -> LocalModelProfile:
        error = self.installation_error()
        if error is not None:
            raise LlmConfigurationError(error, code=error)
        assert self.profile is not None
        return self.profile

    def adapter(self) -> OpenAIModelAdapter:
        profile = self.require_profile()
        endpoint = self.endpoint()
        return OpenAIModelAdapter(
            client=AsyncOpenAI(
                api_key="ollama",
                base_url=endpoint.api_base,
                max_retries=0,
                http_client=create_llm_async_http_client(endpoint=endpoint, timeout=120),
            ),
            model_name=profile.model_name,
            owns_client=True,
            max_output_tokens=LOCAL_MODEL_OUTPUT_TOKENS,
            extra_body={"think": False},
        )

    def endpoint(self) -> ResolvedLlmEndpoint:
        profile = self.require_profile()
        with self._lock:
            if self._closed:
                raise LlmConfigurationError("Local model runtime closed", code="LOCAL_MODEL_START_FAILED")
            try:
                if self._process is not None and self._process.root_exit_code() is None:
                    assert self._endpoint is not None
                    return self._endpoint
                self._stop_process()
                self._endpoint = self._start(profile)
                return self._endpoint
            except (OSError, httpx.HTTPError, ValueError) as exc:
                self._stop_process()
                if isinstance(exc, LlmConfigurationError):
                    raise
                raise LlmConfigurationError(
                    "Local model runtime did not start", code="LOCAL_MODEL_START_FAILED",
                ) from exc

    def _start(self, profile: LocalModelProfile) -> ResolvedLlmEndpoint:
        from engine.local_execution.windows import WindowsProcess

        with socket.socket() as listener:
            listener.bind((_LOOPBACK, 0))
            port = listener.getsockname()[1]
        authority = f"{_LOOPBACK}:{port}"
        base = f"http://{authority}"
        environment = local_environment({
            "OLLAMA_HOST": authority,
            "OLLAMA_MODELS": str(profile.models_dir),
            "OLLAMA_NO_CLOUD": "1",
            "OLLAMA_CONTEXT_LENGTH": str(profile.context_length),
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_KEEP_ALIVE": "5m",
            "OLLAMA_NOPRUNE": "1",
            "USERPROFILE": str(profile.state_dir),
            "TMP": str(profile.scratch_dir),
            "TEMP": str(profile.scratch_dir),
        })
        process = WindowsProcess.launch(
            profile.executable,
            subprocess.list2cmdline([str(profile.executable), "serve"]),
            profile.executable.parent,
            environment,
            interactive=False,
        )
        self._process = process
        self._drain_stop.clear()
        self._drainer = Thread(target=self._drain, args=(process,), daemon=True, name="ollama-output")
        self._drainer.start()
        deadline = time.monotonic() + 20
        with httpx.Client(base_url=base, trust_env=False, follow_redirects=False, timeout=1) as client:
            while time.monotonic() < deadline and process.root_exit_code() is None:
                try:
                    response = client.get("/api/tags")
                    response.raise_for_status()
                except httpx.TransportError:
                    time.sleep(0.15)
                    continue
                models = response.json().get("models", [])
                if not any(
                    model.get("name") == profile.model_name
                    and str(model.get("digest")).removeprefix("sha256:") == profile.model_digest.removeprefix("sha256:")
                    for model in models
                ):
                    raise LlmConfigurationError(
                        "Installed model digest differs from profile", code="LOCAL_MODEL_WEIGHTS_CHANGED",
                    )
                if process.root_exit_code() is None:
                    return ResolvedLlmEndpoint(f"{base}/v1", "http", _LOOPBACK, port, (_LOOPBACK,))
        raise OSError("Managed loopback server did not become ready")

    def _drain(self, process: WindowsProcess) -> None:
        # Ollama's server output is independent of Agent results. Drain its
        # pipes without retaining model requests or spending disk on logs.
        while not self._drain_stop.is_set():
            try:
                out = process.read("stdout", 64 * 1024)
                err = process.read("stderr", 64 * 1024)
            except OSError:
                return
            if out is None and err is None:
                return
            if not out and not err:
                self._drain_stop.wait(0.05)

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        self._endpoint = None
        self._drain_stop.set()
        if self._drainer is not None:
            self._drainer.join()
            self._drainer = None
        if process is not None:
            process.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop_process()
