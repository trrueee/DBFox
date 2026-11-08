from __future__ import annotations

import hashlib
import heapq
import os
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
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


class WorkspaceConflict(WorkspaceError):
    """A fixed, safe precondition failure; no mutation was committed."""


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
    def __init__(self, root: str | Path, *, mutation_database: Path) -> None:
        self._mutation_database = mutation_database
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

    def _entry_path(self, relative_path: str) -> Path:
        """Authorize the parent without replacing the final directory entry."""
        normalized = self.normalize(relative_path)
        if normalized == ".":
            return self.root
        entry = self.root / normalized
        parent = entry.parent.resolve(strict=False)
        if not parent.is_relative_to(self.root):
            raise WorkspaceError("Workspace path escapes the authorized root")
        return parent / entry.name

    @contextmanager
    def _mutation(self) -> Iterator[None]:
        # Tool workers and Dock operations share this owner's existing SQLite
        # file. Its write lock covers hash validation through file replacement,
        # including separate processes; no lock state is stored in the project.
        connection = sqlite3.connect(self._mutation_database, timeout=5.0)
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                raise WorkspaceError("Workspace is busy; retry the operation") from exc
            yield
        finally:
            connection.rollback()
            connection.close()

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

    def search_files(self, query: str, *, path_prefix: str = "", limit: int = 20) -> WorkspaceDirectory:
        if not 1 <= limit <= 100:
            raise WorkspaceError("Search limit must be between 1 and 100")
        directory = self.list_directory(path_prefix) if not query else self._scan_tree(self.resolve(path_prefix))
        needle = query.casefold()
        matches = heapq.nsmallest(
            limit + 1,
            (entry for entry in directory.entries if not needle or needle in entry.relative_path.casefold()),
            key=lambda entry: (not entry.is_dir, entry.relative_path.casefold()),
        )
        return WorkspaceDirectory(tuple(matches[:limit]), directory.truncated or len(matches) > limit)

    def write_text_file(
        self,
        relative_path: str,
        content: str,
        *,
        expected_sha256: str | None = None,
    ) -> WorkspaceFile:
        data = content.encode("utf-8")
        if len(data) > MAX_WORKSPACE_FILE_BYTES:
            raise WorkspaceError("Write exceeds the 1 MiB file limit")
        with self._mutation():
            path = self.resolve(relative_path)
            if path == self.root or (path.exists() and path.is_dir()):
                raise WorkspaceError("Target path is a directory")
            if expected_sha256 is None and path.exists():
                raise WorkspaceConflict("覆盖已有文件前必须先读取并提供当前 sha256。")
            if expected_sha256 is not None and not path.exists():
                raise WorkspaceConflict("原文件已不存在，本次修改未执行。请重新确认目标。")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, prefix=f".{path.name}.",
                    suffix=".tmp", delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if expected_sha256 is not None:
                    # An external editor does not hold our SQLite writer lock.
                    # Validate after staging, immediately before publication.
                    current = self.read_text_file(relative_path)
                    if current.sha256 != expected_sha256:
                        raise WorkspaceConflict("文件已变更，本次修改未执行。请保留当前内容，等待新的修改指令。")
                    os.replace(temporary_path, path)
                elif os.name == "nt":
                    # Windows rename refuses an existing destination, including
                    # one created by an external editor after our preflight.
                    os.rename(temporary_path, path)
                else:
                    # Publish the staged file without replacement on POSIX.
                    os.link(temporary_path, path)
            except FileExistsError as exc:
                raise WorkspaceConflict("目标文件已存在，本次创建未执行。请保留现有内容。") from exc
            except OSError as exc:
                raise WorkspaceError("Workspace file cannot be written") from exc
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            return WorkspaceFile(
                relative_path=self.normalize(relative_path),
                content=content,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                truncated=False,
            )

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
            raise WorkspaceConflict("文件已变更，本次修改未执行。请保留当前内容，等待新的修改指令。")
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
        with self._mutation():
            path = self._entry_path(relative_path)
            if path == self.root:
                raise WorkspaceError("Refusing to delete the workspace root")
            if not os.path.lexists(path):
                raise WorkspaceError("Workspace path does not exist")
            try:
                if path.is_junction() or (path.is_dir() and not path.is_symlink()):
                    path.rmdir()
                else:
                    path.unlink()
            except OSError as exc:
                raise WorkspaceError("Only files and empty directories can be deleted") from exc

    def move_path(self, source_path: str, destination_path: str) -> None:
        with self._mutation():
            source = self._entry_path(source_path)
            destination = self._entry_path(destination_path)
            if source == self.root or destination == self.root:
                raise WorkspaceError("Refusing to move the workspace root")
            if not os.path.lexists(source):
                raise WorkspaceError("Source path does not exist")
            if os.path.lexists(destination):
                raise WorkspaceConflict("目标路径已存在，本次移动未执行。")
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                source.rename(destination)
            except FileExistsError as exc:
                raise WorkspaceConflict("目标路径已存在，本次移动未执行。") from exc
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
        directory = None if start.is_file() else self._scan_tree(start)
        candidates: Iterator[Path] = iter((start,)) if directory is None else (
            self.root / entry.relative_path for entry in directory.entries if not entry.is_dir
        )
        matches: list[WorkspaceGrepMatch] = []
        scanned_files = 0
        scanned_bytes = 0
        truncated = directory.truncated if directory is not None else False
        needle = query.casefold()
        for path in candidates:
            if scanned_files >= MAX_GREP_FILES or scanned_bytes >= MAX_GREP_BYTES:
                truncated = True
                break
            scanned_files += 1
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_WORKSPACE_FILE_BYTES or scanned_bytes + size > MAX_GREP_BYTES:
                truncated = True
                continue
            try:
                with path.open("rb") as stream:
                    data = stream.read(min(MAX_WORKSPACE_FILE_BYTES + 1, MAX_GREP_BYTES - scanned_bytes))
                scanned_bytes += len(data)
                if (
                    len(data) > MAX_WORKSPACE_FILE_BYTES
                    or len(data) < size
                ):
                    truncated = True
                    continue
                if b"\0" in data[:8192]:
                    continue
                text = data.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
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

    def _scan_tree(self, start: Path) -> WorkspaceDirectory:
        """Bound all entries, including empty directories, before reading content."""
        if not start.is_dir():
            raise WorkspaceError("Search directory does not exist")
        pending = [start]
        entries: list[WorkspaceEntry] = []
        scanned = 0
        truncated = False
        while pending:
            directory = pending.pop()
            try:
                if not directory.resolve(strict=True).is_relative_to(self.root):
                    truncated = True
                    continue
                with os.scandir(directory) as iterator:
                    children = []
                    for item in iterator:
                        scanned += 1
                        if scanned > MAX_WORKSPACE_DIR_SCAN_ENTRIES:
                            return WorkspaceDirectory(tuple(entries), True)
                        try:
                            path = Path(item.path)
                            canonical = path.resolve(strict=True)
                            if not canonical.is_relative_to(self.root):
                                continue
                            is_dir = canonical.is_dir()
                            if is_dir and item.name in _SKIPPED_DIR_NAMES:
                                continue
                            if not is_dir and not canonical.is_file():
                                continue
                            entries.append(WorkspaceEntry(item.name, path.relative_to(self.root).as_posix(), is_dir))
                            if is_dir and not item.is_symlink() and not path.is_junction():
                                children.append(path)
                        except (OSError, RuntimeError):
                            truncated = True
                    pending.extend(sorted(children, reverse=True))
            except (OSError, RuntimeError) as exc:
                if directory == start:
                    raise WorkspaceError("Search directory cannot be read") from exc
                truncated = True
        return WorkspaceDirectory(tuple(sorted(entries, key=lambda entry: entry.relative_path.casefold())), truncated)


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
