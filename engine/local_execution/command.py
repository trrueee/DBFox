"""Resolve the exact Windows launch reviewed by the user."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from engine.json_codec import canonical_dumps
from engine.local_execution.contracts import StartInput

_ENVIRONMENT_KEYS = frozenset({
    "APPDATA", "COMSPEC", "DOTNET_ROOT", "GOPATH", "GOROOT", "HOMEDRIVE", "HOMEPATH",
    "JAVA_HOME", "LANG", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "NVM_HOME",
    "NVM_SYMLINK", "PATH", "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "SYSTEMDRIVE", "SYSTEMROOT",
    "TEMP", "TMP", "USERPROFILE", "VIRTUAL_ENV", "WINDIR",
})
_SHELL_FLAGS = '/d /s /v:off /c'


class ExecutionError(ValueError):
    """Expected local-execution failure with a user-safe message."""


def local_environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = {key.upper(): value for key, value in os.environ.items() if key.upper() in _ENVIRONMENT_KEYS}
    env.update({key.upper(): value for key, value in (overrides or {}).items()})
    # Resolve bare executable names from absolute PATH entries only. An empty
    # entry or implicit CWD lookup changes what the user is authorizing.
    frozen_root = getattr(sys, "_MEIPASS", None)
    paths = []
    for raw in env.get("PATH", "").split(os.pathsep):
        entry = Path(raw.strip('"'))
        if entry.is_absolute() and (not frozen_root or not entry.is_relative_to(frozen_root)):
            paths.append(str(entry))
    env["PATH"] = os.pathsep.join(paths)
    return env


def find_program(name: str, directory: Path, environment: dict[str, str], *, scripts: bool = False) -> Path:
    candidate = Path(name)
    candidates: tuple[Path, ...]
    if candidate.is_absolute() or candidate.parent != Path(".") or "/" in name or "\\" in name:
        if candidate.drive and not candidate.is_absolute():
            raise ExecutionError("Use an absolute executable path or a path relative to the command directory.")
        candidates = (directory / candidate,)
    else:
        extensions = (".exe", ".cmd", ".bat") if scripts else (".exe",)
        names = (name,) if candidate.suffix else tuple(name + ext for ext in extensions)
        candidates = tuple(
            path / filename
            for entry in environment.get("PATH", "").split(os.pathsep) if entry
            for path in (Path(entry),)
            for filename in names
        )
    for path in candidates:
        if path.is_file():
            resolved = path.resolve(strict=True)
            if resolved.suffix.lower() == ".exe" or (
                scripts and resolved.suffix.lower() in {".cmd", ".bat"}
            ):
                return resolved
            raise ExecutionError("Direct execution requires an .exe. Use an explicit shell_script for .cmd or .bat.")
    raise ExecutionError("Executable not found in the selected directory or the Sidecar's PATH.")


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    input: StartInput
    program: Path
    directory: Path
    environment: dict[str, str]
    identity: tuple[int, int, int, int]
    command_line: str

    def display(self) -> dict:
        return {
            "executable": str(self.program),
            "cwd": str(self.directory),
            "mode": "windows_cmd" if self.input.shell_script is not None else "direct",
            "shell_flags": _SHELL_FLAGS if self.input.shell_script is not None else None,
            "lifetime": self.input.lifetime,
            "timeout_seconds": self.input.timeout_seconds,
            "interactive": self.input.interactive,
        }

    def subject(self) -> dict:
        return {
            **self.display(),
            "command": self.input.model_dump(mode="json"),
            "executable_identity": list(self.identity),
            "environment_digest": hashlib.sha256(canonical_dumps(self.environment).encode()).hexdigest(),
        }


def prepare(input: StartInput, directory: Path) -> PreparedCommand:
    from engine.local_execution.windows import command_shell

    environment = local_environment(input.env)
    # Use the Windows system shell, including for tools that look up COMSPEC.
    shell = command_shell().resolve(strict=True)
    environment["COMSPEC"] = str(shell)
    if input.shell_script is None:
        program = find_program(input.argv[0], directory, environment)
        if program.name.casefold() == "cmd.exe":
            raise ExecutionError("Use shell_script to run Windows cmd with explicit shell approval.")
        command_line = subprocess.list2cmdline([str(program), *input.argv[1:]])
    else:
        program = shell
        # cmd's /s rule removes the surrounding pair. The contents are the
        # complete, explicitly approved cmd script, with cmd's own syntax.
        command_line = f'"{program}" {_SHELL_FLAGS} "{input.shell_script}"'
        if len(command_line.encode("utf-16-le")) // 2 >= 8191:
            raise ExecutionError("The cmd script exceeds the Windows shell limit.")
    if len(command_line.encode("utf-16-le")) // 2 >= 32767:
        raise ExecutionError("The command exceeds the Windows process command line limit.")
    metadata = program.stat()
    return PreparedCommand(
        input, program, directory, environment,
        (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns), command_line,
    )
