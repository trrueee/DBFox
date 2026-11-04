from __future__ import annotations

import hashlib
import heapq
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

MAX_WORKSPACE_FILE_BYTES = 1024 * 1024
MAX_WORKSPACE_DIR_ENTRIES = 600
MAX_WORKSPACE_DIR_SCAN_ENTRIES = 10_000
MAX_GREP_FILES = 2_000
MAX_GREP_BYTES = 8 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
MAX_COMMAND_STREAM_BYTES = 8 * 1024 * 1024
MAX_COMMAND_TIMEOUT_SECONDS = 300
_SKIPPED_DIR_NAMES = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", "target",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})
_COMMAND_ENV_ALLOWLIST = frozenset({
    "COLORTERM",
    "COMSPEC",
    "DOTNET_ROOT",
    "GOPATH",
    "GOROOT",
    "HOME",
    "JAVA_HOME",
    "LANG",
    "NUMBER_OF_PROCESSORS",
    "NVM_HOME",
    "NVM_SYMLINK",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "USERPROFILE",
    "VIRTUAL_ENV",
    "WINDIR",
})


class WorkspaceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    name: str
    relative_path: str
    is_dir: bool


@dataclass(frozen=True, slots=True)
class WorkspaceDirectory:
    entries: tuple[WorkspaceEntry, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    relative_path: str
    content: str
    size_bytes: int
    sha256: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class WorkspaceGrepMatch:
    relative_path: str
    line_number: int
    line: str


@dataclass(frozen=True, slots=True)
class WorkspaceGrepResult:
    matches: tuple[WorkspaceGrepMatch, ...]
    scanned_files: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class CommandRunResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    output: str
    truncated: bool
    output_limit_exceeded: bool


class WorkspaceService:
    def __init__(self, root: str | Path) -> None:
        try:
            self.root = Path(root).expanduser().resolve(strict=True)
        except OSError as exc:
            raise WorkspaceError("Workspace root is unavailable") from exc
        if not self.root.is_dir():
            raise WorkspaceError("Workspace root is not a directory")

    @property
    def root_digest(self) -> str:
        return hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def normalize(relative_path: str) -> str:
        value = str(relative_path or "").strip().replace("\\", "/")
        if not value:
            return "."
        if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
            raise WorkspaceError("Workspace path must be relative")
        parts: list[str] = []
        for part in value.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                raise WorkspaceError("Workspace path must not contain '..'")
            parts.append(part)
        return "/".join(parts) if parts else "."

    def resolve(self, relative_path: str) -> Path:
        normalized = self.normalize(relative_path)
        candidate = (self.root / normalized).resolve(strict=False)
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise WorkspaceError("Workspace path escapes the authorized root")
        return candidate

    def list_directory(self, relative_path: str = "") -> WorkspaceDirectory:
        directory = self.resolve(relative_path)
        if not directory.exists() or not directory.is_dir():
            raise WorkspaceError("Workspace directory does not exist")
        scanned = 0
        candidates: list[WorkspaceEntry] = []
        with os.scandir(directory) as iterator:
            for item in iterator:
                scanned += 1
                if scanned > MAX_WORKSPACE_DIR_SCAN_ENTRIES:
                    break
                try:
                    is_dir = item.is_dir(follow_symlinks=False) or (
                        item.is_symlink() and Path(item.path).resolve(strict=True).is_dir()
                    )
                except OSError:
                    continue
                if is_dir and item.name in _SKIPPED_DIR_NAMES:
                    continue
                parent = self.normalize(relative_path)
                child = item.name if parent == "." else f"{parent}/{item.name}"
                candidates.append(WorkspaceEntry(item.name, child, is_dir))
        entries = heapq.nsmallest(
            MAX_WORKSPACE_DIR_ENTRIES,
            candidates,
            key=lambda entry: (not entry.is_dir, entry.name.casefold()),
        )
        return WorkspaceDirectory(
            entries=tuple(entries),
            truncated=(
                scanned > MAX_WORKSPACE_DIR_SCAN_ENTRIES
                or len(candidates) > MAX_WORKSPACE_DIR_ENTRIES
            ),
        )

    def read_text_file(self, relative_path: str) -> WorkspaceFile:
        path = self.resolve(relative_path)
        if not path.exists() or not path.is_file():
            raise WorkspaceError("Workspace file does not exist")
        try:
            size = path.stat().st_size
            if size > MAX_WORKSPACE_FILE_BYTES:
                raise WorkspaceError("Workspace file exceeds the 1 MiB read limit")
            with path.open("rb") as stream:
                data = stream.read(MAX_WORKSPACE_FILE_BYTES + 1)
            if len(data) > MAX_WORKSPACE_FILE_BYTES:
                raise WorkspaceError("Workspace file exceeds the 1 MiB read limit")
        except WorkspaceError:
            raise
        except OSError as exc:
            raise WorkspaceError("Workspace file cannot be read") from exc
        if any(byte == 0 for byte in data[:8192]):
            raise WorkspaceError("Workspace binary file cannot be read as text")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Workspace file is not UTF-8 text") from exc
        return WorkspaceFile(
            relative_path=self.normalize(relative_path),
            content=content,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            truncated=False,
        )

    def write_text_file(
        self,
        relative_path: str,
        content: str,
        *,
        expected_sha256: str | None = None,
    ) -> WorkspaceFile:
        path = self.resolve(relative_path)
        if path == self.root or (path.exists() and path.is_dir()):
            raise WorkspaceError("Target path is a directory")
        data = content.encode("utf-8")
        if len(data) > MAX_WORKSPACE_FILE_BYTES:
            raise WorkspaceError("Write exceeds the 1 MiB file limit")
        if expected_sha256 is not None:
            if not path.exists():
                raise WorkspaceError("Expected file does not exist")
            current = self.read_text_file(relative_path)
            if current.sha256 != expected_sha256:
                raise WorkspaceError("File changed since it was read")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                temporary_path = Path(stream.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise WorkspaceError("Workspace file cannot be written") from exc
        return self.read_text_file(relative_path)

    def edit_text_file(
        self,
        relative_path: str,
        *,
        old_string: str,
        new_string: str,
        expected_sha256: str,
        replace_all: bool = False,
    ) -> WorkspaceFile:
        snapshot = self.read_text_file(relative_path)
        if snapshot.truncated:
            raise WorkspaceError("Files larger than 1 MiB cannot be edited")
        if snapshot.sha256 != expected_sha256:
            raise WorkspaceError("File changed since it was read")
        if not old_string:
            raise WorkspaceError("old_string must not be empty")
        occurrences = snapshot.content.count(old_string)
        if occurrences == 0:
            raise WorkspaceError("old_string was not found")
        if occurrences > 1 and not replace_all:
            raise WorkspaceError(
                f"old_string occurs {occurrences} times; use a unique anchor or replace_all"
            )
        if old_string == new_string:
            raise WorkspaceError("old_string and new_string are identical")
        updated = snapshot.content.replace(
            old_string,
            new_string,
            -1 if replace_all else 1,
        )
        return self.write_text_file(
            relative_path,
            updated,
            expected_sha256=expected_sha256,
        )

    def delete_path(self, relative_path: str) -> None:
        path = self.resolve(relative_path)
        if path == self.root:
            raise WorkspaceError("Refusing to delete the workspace root")
        if not path.exists():
            raise WorkspaceError("Workspace path does not exist")
        try:
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()
        except OSError as exc:
            raise WorkspaceError("Only files and empty directories can be deleted") from exc

    def move_path(self, source_path: str, destination_path: str) -> None:
        source = self.resolve(source_path)
        destination = self.resolve(destination_path)
        if source == self.root or destination == self.root:
            raise WorkspaceError("Refusing to move the workspace root")
        if not source.exists():
            raise WorkspaceError("Source path does not exist")
        if destination.exists():
            raise WorkspaceError("Destination path already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.replace(destination)
        except OSError as exc:
            raise WorkspaceError("Workspace path cannot be moved") from exc

    def grep_text_files(
        self,
        query: str,
        *,
        path_prefix: str = "",
        limit: int = 50,
    ) -> WorkspaceGrepResult:
        if not query:
            raise WorkspaceError("Search query must not be empty")
        start = self.resolve(path_prefix)
        if not start.exists():
            raise WorkspaceError("Search path does not exist")
        candidates: Iterator[Path] = iter((start,)) if start.is_file() else self._walk_files(start)
        matches: list[WorkspaceGrepMatch] = []
        scanned_files = 0
        scanned_bytes = 0
        truncated = False
        needle = query.casefold()
        for path in candidates:
            if scanned_files >= MAX_GREP_FILES or scanned_bytes >= MAX_GREP_BYTES:
                truncated = True
                break
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_WORKSPACE_FILE_BYTES or scanned_bytes + size > MAX_GREP_BYTES:
                truncated = True
                continue
            try:
                with path.open("rb") as stream:
                    data = stream.read(MAX_WORKSPACE_FILE_BYTES + 1)
                if (
                    len(data) > MAX_WORKSPACE_FILE_BYTES
                    or scanned_bytes + len(data) > MAX_GREP_BYTES
                ):
                    truncated = True
                    continue
                if b"\0" in data[:8192]:
                    continue
                text = data.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scanned_files += 1
            scanned_bytes += len(data)
            relative_path = path.relative_to(self.root).as_posix()
            for line_number, line in enumerate(text.splitlines(), start=1):
                if needle in line.casefold():
                    matches.append(WorkspaceGrepMatch(
                        relative_path=relative_path,
                        line_number=line_number,
                        line=line[:500],
                    ))
                    if len(matches) >= limit:
                        return WorkspaceGrepResult(tuple(matches), scanned_files, True)
        return WorkspaceGrepResult(tuple(matches), scanned_files, truncated)

    def run_command(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str = "",
        timeout_seconds: int = 60,
    ) -> CommandRunResult:
        if not argv or any(not value or "\0" in value for value in argv):
            raise WorkspaceError("Command argv must contain non-empty strings")
        if not 1 <= timeout_seconds <= MAX_COMMAND_TIMEOUT_SECONDS:
            raise WorkspaceError("Command timeout must be between 1 and 300 seconds")
        command_cwd = self.resolve(cwd)
        if not command_cwd.is_dir():
            raise WorkspaceError("Command cwd is not a workspace directory")
        started = time.monotonic()
        timed_out = False
        exit_code: int | None = None
        output = bytearray()
        output_bytes = [0]
        output_limit = threading.Event()
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(command_cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                env=_command_environment(),
                creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise WorkspaceError("Command could not be started") from exc
        reader = threading.Thread(
            target=_read_command_output,
            args=(process.stdout, output, output_bytes, output_limit),
            name="dbfox-workspace-command-output",
            daemon=True,
        )
        reader.start()
        deadline = started + timeout_seconds
        while process.poll() is None:
            if output_limit.is_set():
                _terminate_process_tree(process)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _terminate_process_tree(process)
                break
            time.sleep(0.01)
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
        reader.join(timeout=1.0)
        if reader.is_alive():
            _terminate_process_tree(process)
            raise WorkspaceError("Command output could not be collected")
        if not timed_out and not output_limit.is_set():
            exit_code = int(process.returncode)
        raw_output = bytes(output)
        duration_ms = int((time.monotonic() - started) * 1_000)
        return CommandRunResult(
            argv=argv,
            cwd=self.normalize(cwd),
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=duration_ms,
            output=raw_output.decode("utf-8", errors="replace"),
            truncated=(
                output_bytes[0] > MAX_COMMAND_OUTPUT_BYTES
                or output_limit.is_set()
            ),
            output_limit_exceeded=output_limit.is_set(),
        )

    def _walk_files(self, start: Path) -> Iterator[Path]:
        for root, directories, names in os.walk(start, followlinks=False):
            directories[:] = sorted(
                name for name in directories if name not in _SKIPPED_DIR_NAMES
            )
            for name in sorted(names):
                path = Path(root) / name
                try:
                    canonical = path.resolve(strict=True)
                except OSError:
                    continue
                if canonical.is_relative_to(self.root) and canonical.is_file():
                    yield canonical


def _read_command_output(
    stream: object,
    tail: bytearray,
    total: list[int],
    output_limit: threading.Event,
) -> None:
    read = getattr(stream, "read", None)
    close = getattr(stream, "close", None)
    if not callable(read):
        return
    try:
        while not output_limit.is_set():
            chunk = read(64 * 1024)
            if not chunk:
                break
            total[0] += len(chunk)
            tail.extend(chunk)
            if len(tail) > MAX_COMMAND_OUTPUT_BYTES:
                del tail[:-MAX_COMMAND_OUTPUT_BYTES]
            if total[0] > MAX_COMMAND_STREAM_BYTES:
                output_limit.set()
                break
    except (OSError, ValueError):
        pass
    finally:
        if callable(close):
            try:
                close()
            except OSError:
                pass


def _command_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _COMMAND_ENV_ALLOWLIST or key.upper().startswith("LC_")
    }


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            killpg = getattr(os, "killpg", None)
            getpgid = getattr(os, "getpgid", None)
            sigkill = getattr(signal, "SIGKILL", None)
            if not callable(killpg) or not callable(getpgid) or sigkill is None:
                raise OSError("process group termination is unavailable")
            killpg(getpgid(process.pid), sigkill)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
