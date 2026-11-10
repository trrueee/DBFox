from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ContextManager, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.resource import ResourceScopeRef

WORKSPACE_KIND = "dbfox.workspace.root"
LOG_CHUNK_BYTES = 4096
JobState = Literal["starting", "running", "stopping", "exited", "start_failed",
                   "cancelled", "timed_out", "interrupted", "unknown"]
ACTIVE_STATES = ("starting", "running", "stopping")


class WorkspaceDirectory(Protocol):
    """A resolved Workspace resource can fence a path through process creation."""

    def command_directory(self, relative_path: str) -> Path: ...

    def execution_directory(self, relative_path: str) -> ContextManager[Path]: ...


@dataclass(frozen=True, slots=True)
class ExecutionScope:
    session_id: str
    workspace: ResourceScopeRef


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StartInput(Contract):
    argv: list[str] = Field(
        default_factory=list, max_length=128,
        description="Executable and arguments for direct execution. Omit shell_script when using argv.",
    )
    shell_script: str | None = Field(
        default=None, min_length=1, max_length=8000,
        description="Optional Windows cmd script. Omit this field when using argv.",
    )
    cwd: str = Field(
        default="", max_length=1024,
        description="Existing directory relative to the bound project root. Leave empty or use . for that root.",
    )
    timeout_seconds: int = Field(default=300, ge=1, le=7200)
    lifetime: Literal["foreground", "background"] = "foreground"
    interactive: bool = False
    env: dict[
        Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")],
        Annotated[str, Field(max_length=1024)],
    ] = Field(default_factory=dict, max_length=16, description="Explicit non-secret environment overrides, reviewed with the command.")

    @model_validator(mode="after")
    def validate_command(self) -> StartInput:
        if bool(self.argv) == bool(self.shell_script):
            raise ValueError("Specify one of argv (direct execution) or shell_script (Windows cmd)")
        if self.argv and (not self.argv[0].strip() or sum(map(len, self.argv)) > 8000):
            raise ValueError("The executable name and arguments must fit the command limit")
        if any("\0" in value for value in (*self.argv, self.shell_script or "", self.cwd)):
            raise ValueError("Command fields cannot contain a NUL character")
        keys = {key.upper() for key in self.env}
        if len(keys) != len(self.env) or sum(map(len, self.env.values())) > 4096:
            raise ValueError("Environment overrides must use unique names and fit the command budget")
        if any(
            key in {"COMSPEC", "SYSTEMROOT", "WINDIR", "PATHEXT"}
            or key.startswith(("DBFOX_", "_PYI", "PYINSTALLER_"))
            or key.endswith(("_KEY", "_TOKEN", "_PASSWORD", "_SECRET"))
            or key in {"PASSWORD", "TOKEN", "SECRET"}
            for key in keys
        ) or any("\0" in value for value in self.env.values()):
            raise ValueError("Environment overrides cannot set system launch fields, credentials, or DBFox runtime settings")
        return self


class JobView(Contract):
    id: str
    run_id: str
    state: JobState
    reason: str | None
    executable: str
    argv: list[str]
    shell_script: str | None
    cwd: str
    lifetime: Literal["foreground", "background"]
    interactive: bool
    stdin_open: bool
    timeout_seconds: int
    root_exit_code: int | None
    active_processes: int | None
    output_finalized: bool
    first_cursor: int
    last_cursor: int
    retained_bytes: int
    duration_ms: int


class LogLine(Contract):
    cursor: int
    stream: Literal["stdout", "stderr"]
    text: str


class JobPage(Contract):
    job: JobView
    chunks: list[LogLine]
    next_cursor: int
    cursor_expired: bool
    has_more: bool


class JobInput(Contract):
    job_id: str = Field(pattern=r"^job_[0-9a-f]{32}$")


class InspectInput(JobInput):
    after: int = Field(default=0, ge=0, le=2**53 - 1)
    tail: bool = False
    wait_seconds: int = Field(default=0, ge=0, le=15)


class StdinInput(JobInput):
    text: str = Field(default="", max_length=4096)
    close: bool = False

    @model_validator(mode="after")
    def validate_write(self) -> StdinInput:
        if (not self.text and not self.close) or len(self.text.encode("utf-8")) > LOG_CHUNK_BYTES:
            raise ValueError("Specify a write of up to 4096 UTF-8 bytes or close stdin")
        return self
