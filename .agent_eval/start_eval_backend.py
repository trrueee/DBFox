#!/usr/bin/env python3
"""Start a stable eval backend (uvicorn without reload) and wait for health.

Writes stdout/stderr logs and pid file under .agent_eval/.
"""
import os
import sys
import time
import subprocess
import signal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
STDOUT = ROOT / "backend_eval_stdout.log"
STDERR = ROOT / "backend_eval_stderr.log"
PIDFILE = ROOT / "backend_eval.pid"
HEALTH_URL = "http://127.0.0.1:18625/api/v1/health"


def clean_env_for_windows(env: dict) -> dict:
    # Ensure only one Path/PATH key on Windows
    new_env = env.copy()
    if os.name == "nt":
        path_keys = [k for k in list(new_env.keys()) if k.lower() == "path"]
        if len(path_keys) > 1:
            keep = path_keys[0]
            value = new_env.get(keep)
            # remove all then set canonical 'Path'
            for k in path_keys:
                new_env.pop(k, None)
            # set canonical casing
            new_env["Path"] = value
    return new_env


def tail(file: Path, n=200):
    if not file.exists():
        return ""
    try:
        with file.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 1024
            data = b""
            while size > 0 and len(data) < n * 80:
                seek = max(0, size - block)
                f.seek(seek)
                chunk = f.read(min(block, size))
                data = chunk + data
                size = seek
            return data.decode(errors="ignore")[-8000:]
    except Exception:
        return ""


def main():
    env = os.environ.copy()
    env = clean_env_for_windows(env)

    # Ensure LLM config is present for P1 targeted runs when required.
    # Read possible local config overrides from .agent_eval/config.local.json
    try:
        cfg_path = ROOT / "config.local.json"
        if cfg_path.exists():
            import json as _json

            with cfg_path.open("r", encoding="utf-8") as fh:
                cfg = _json.load(fh)
            llm = cfg.get("llm") if isinstance(cfg, dict) else None
            if isinstance(llm, dict):
                # merge known keys into env if not already present
                if "provider" in llm and "DATABOX_LLM_PROVIDER" not in env:
                    env["DATABOX_LLM_PROVIDER"] = str(llm.get("provider"))
                if "model_name" in llm and "DATABOX_LLM_MODEL" not in env:
                    env["DATABOX_LLM_MODEL"] = str(llm.get("model_name"))
                if "api_key" in llm and "DATABOX_LLM_API_KEY" not in env:
                    env["DATABOX_LLM_API_KEY"] = str(llm.get("api_key"))
                if "api_base" in llm and "DATABOX_LLM_API_BASE" not in env:
                    env["DATABOX_LLM_API_BASE"] = str(llm.get("api_base"))
            else:
                # legacy flat keys
                for k in ("DATABOX_LLM_PROVIDER", "DATABOX_LLM_MODEL", "OPENAI_API_KEY", "DASHSCOPE_API_KEY", "DATABOX_LLM_API_KEY"):
                    if k in cfg and k not in env:
                        env[k] = str(cfg[k])
    except Exception:
        pass

    cmd = [sys.executable, "-m", "uvicorn", "engine.main:app", "--host", "127.0.0.1", "--port", "18625", "--log-level", "info"]

    STDOUT.parent.mkdir(parents=True, exist_ok=True)

    out_f = open(STDOUT, "a", encoding="utf-8")
    err_f = open(STDERR, "a", encoding="utf-8")

    print("Starting uvicorn engine.main:app (no reload)...")
    proc = subprocess.Popen(cmd, stdout=out_f, stderr=err_f, env=env)

    PIDFILE.write_text(str(proc.pid), encoding="utf-8")

    # wait for health
    deadline = time.time() + 60.0
    client = httpx.Client(timeout=5.0)
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                print("Backend process exited prematurely. Tailing stderr:")
                print(tail(STDERR, n=400))
                sys.exit(1)
            try:
                r = client.get(HEALTH_URL)
                if r.status_code == 200:
                    print("Backend healthy and listening.")
                    print(f"pid: {proc.pid}")
                    sys.exit(0)
            except Exception:
                pass
            time.sleep(0.5)
        print("Timeout waiting for backend health. Tailing stderr:")
        print(tail(STDERR, n=400))
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
