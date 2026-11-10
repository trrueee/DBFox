"""Win32 process creation and handle ownership for Windows 11 x64."""

from __future__ import annotations

import ctypes
import msvcrt
import os
from ctypes import wintypes as win
from pathlib import Path
from threading import Lock

_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_size = ctypes.c_size_t
_ptr = ctypes.c_void_p
_handle = win.HANDLE
_dword = win.DWORD
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
_PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
_CREATE_FLAGS = 0x00080000 | 0x08000000 | 0x00000400  # Extended startup, no console, Unicode env.
_STARTF_USESTDHANDLES = 0x100
_WAIT_TIMEOUT = 258
_PIPE_EOF = {109, 232, 233}
_WINDOWS_BINARY_TYPES = {0, 6}  # SCS_32BIT_BINARY and SCS_64BIT_BINARY.
_ERROR_BAD_EXE_FORMAT = 193
_NO_ERROR_DIALOGS = 0x0001 | 0x0002 | 0x8000
_creation_lock = Lock()


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", _dword), ("min_ws", _size), ("max_ws", _size),
        ("active_limit", _dword), ("affinity", _size),
        ("priority", _dword), ("scheduling", _dword),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimit), ("io_counters", ctypes.c_uint64 * 6),
        ("process_memory", _size), ("job_memory", _size),
        ("peak_process_memory", _size), ("peak_job_memory", _size),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_int64), ("kernel_time", ctypes.c_int64),
        ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
        ("page_faults", _dword), ("total", _dword), ("active", _dword),
        ("terminated", _dword),
    ]


class _Startup(ctypes.Structure):
    _fields_ = [
        ("size", _dword), ("reserved", win.LPWSTR), ("desktop", win.LPWSTR),
        ("title", win.LPWSTR), ("x", _dword), ("y", _dword),
        ("x_size", _dword), ("y_size", _dword), ("cols", _dword), ("rows", _dword),
        ("fill", _dword), ("flags", _dword), ("show_window", win.WORD),
        ("reserved2_count", win.WORD), ("reserved2", _ptr),
        ("stdin", _handle), ("stdout", _handle), ("stderr", _handle),
    ]


class _StartupEx(ctypes.Structure):
    _fields_ = [("base", _Startup), ("attributes", _ptr)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", _handle), ("thread", _handle), ("pid", _dword), ("tid", _dword)]


def _api(name, restype, *argtypes):
    function = getattr(_kernel, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


_create_job = _api("CreateJobObjectW", _handle, _ptr, win.LPCWSTR)
_set_job = _api("SetInformationJobObject", win.BOOL, _handle, ctypes.c_int, _ptr, _dword)
_query_job = _api("QueryInformationJobObject", win.BOOL, _handle, ctypes.c_int, _ptr, _dword, _ptr)
_terminate_job = _api("TerminateJobObject", win.BOOL, _handle, win.UINT)
_init_attrs = _api("InitializeProcThreadAttributeList", win.BOOL, _ptr, _dword, _dword, ctypes.POINTER(_size))
_set_attr = _api("UpdateProcThreadAttribute", win.BOOL, _ptr, _dword, _size, _ptr, _size, _ptr, _ptr)
_delete_attrs = _api("DeleteProcThreadAttributeList", None, _ptr)
_create_process = _api(
    "CreateProcessW", win.BOOL, win.LPCWSTR, win.LPWSTR, _ptr, _ptr, win.BOOL, _dword,
    _ptr, win.LPCWSTR, ctypes.POINTER(_StartupEx), ctypes.POINTER(_ProcessInfo),
)
_close = _api("CloseHandle", win.BOOL, _handle)
_wait = _api("WaitForSingleObject", _dword, _handle, _dword)
_exit_code = _api("GetExitCodeProcess", win.BOOL, _handle, ctypes.POINTER(_dword))
_peek_pipe = _api("PeekNamedPipe", win.BOOL, _handle, _ptr, _dword, _ptr, ctypes.POINTER(_dword), _ptr)
_system_directory = _api("GetSystemDirectoryW", win.UINT, win.LPWSTR, win.UINT)
_get_dll_directory = _api("GetDllDirectoryW", _dword, _dword, win.LPWSTR)
_set_dll_directory = _api("SetDllDirectoryW", win.BOOL, win.LPCWSTR)
_get_binary_type = _api("GetBinaryTypeW", win.BOOL, win.LPCWSTR, ctypes.POINTER(_dword))
_get_thread_error_mode = _api("GetThreadErrorMode", _dword)
_set_thread_error_mode = _api("SetThreadErrorMode", win.BOOL, _dword, ctypes.POINTER(_dword))


def _checked(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def command_shell() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    size = _checked(_system_directory(buffer, len(buffer)))
    if size >= len(buffer):
        raise OSError("Windows system directory is too long")
    return Path(buffer.value) / "cmd.exe"


class WindowsProcess:
    """Own a Job Object and the parent's standard stream endpoints."""

    def __init__(self, job: int, process: int, stdin: int, stdout: int, stderr: int) -> None:
        self._job: int | None = job
        self._process = process
        self._stdin: int | None = stdin
        self._readers = {"stdout": stdout, "stderr": stderr}
        self._job_lock = Lock()
        self._stdin_lock = Lock()

    @classmethod
    def launch(
        cls, program: Path, command_line: str, directory: Path, environment: dict[str, str],
        *, interactive: bool,
    ) -> WindowsProcess:
        job = _checked(_create_job(None, None))
        descriptors: list[int] = []
        attributes = None
        info = _ProcessInfo()
        try:
            limits = _ExtendedLimit()
            limits.basic.flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _checked(_set_job(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)))
            for _ in range(3):
                descriptors.extend(os.pipe())
            child_in, parent_in, parent_out, child_out, parent_err, child_err = descriptors
            for fd in descriptors:
                msvcrt.setmode(fd, os.O_BINARY)
            child_fds = (child_in, child_out, child_err)
            stream_handles = (_handle * 3)(*(msvcrt.get_osfhandle(fd) for fd in child_fds))
            job_handles = (_handle * 1)(job)
            size = _size()
            _init_attrs(None, 2, 0, ctypes.byref(size))
            _checked(size.value)
            buffer = ctypes.create_string_buffer(size.value)
            _checked(_init_attrs(buffer, 2, 0, ctypes.byref(size)))
            attributes = buffer
            _checked(_set_attr(attributes, 0, _PROC_THREAD_ATTRIBUTE_JOB_LIST,
                               ctypes.byref(job_handles), ctypes.sizeof(job_handles), None, None))
            _checked(_set_attr(attributes, 0, _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                               ctypes.byref(stream_handles), ctypes.sizeof(stream_handles), None, None))

            startup = _StartupEx()
            startup.base.size = ctypes.sizeof(startup)
            startup.base.flags = _STARTF_USESTDHANDLES
            startup.base.stdin, startup.base.stdout, startup.base.stderr = stream_handles
            startup.attributes = ctypes.cast(attributes, _ptr)
            command_buffer = ctypes.create_unicode_buffer(command_line)
            environment_buffer = ctypes.create_unicode_buffer("\0".join(
                f"{key}={value}" for key, value in sorted(environment.items(), key=lambda item: item[0].upper())
            ) + "\0\0")
            with _creation_lock:
                previous_mode = _dword()
                _checked(_set_thread_error_mode(_get_thread_error_mode() | _NO_ERROR_DIALOGS, ctypes.byref(previous_mode)))
                try:
                    # Reject malformed files before CreateProcess can enter
                    # interactive compatibility handling on the broker thread.
                    binary_type = _dword()
                    _checked(_get_binary_type(str(program), ctypes.byref(binary_type)))
                    if binary_type.value not in _WINDOWS_BINARY_TYPES:
                        raise ctypes.WinError(_ERROR_BAD_EXE_FORMAT)
                    # The frozen Sidecar's private DLL directory would otherwise
                    # be inherited by the external program.
                    dll_directory = ctypes.create_unicode_buffer(32768)
                    dll_length = _get_dll_directory(len(dll_directory), dll_directory)
                    if dll_length >= len(dll_directory):
                        raise OSError("Windows DLL search directory is too long")
                    if dll_length:
                        _checked(_set_dll_directory(None))
                    try:
                        for fd in child_fds:
                            os.set_inheritable(fd, True)
                        try:
                            _checked(_create_process(
                                str(program), command_buffer, None, None, True, _CREATE_FLAGS,
                                ctypes.cast(environment_buffer, _ptr), str(directory), ctypes.byref(startup),
                                ctypes.byref(info),
                            ))
                        finally:
                            for fd in child_fds:
                                os.close(fd)
                                descriptors.remove(fd)
                    finally:
                        if dll_length:
                            _checked(_set_dll_directory(dll_directory.value))
                finally:
                    _checked(_set_thread_error_mode(previous_mode, None))

            result = cls(job, info.process, parent_in, parent_out, parent_err)
            if not interactive:
                result.close_stdin()
            descriptors.clear()
            info.process = None
            job = None
            return result
        finally:
            if job:
                _close(job)
            for handle in (info.thread, info.process):
                if handle:
                    _close(handle)
            if attributes is not None:
                _delete_attrs(attributes)
            for fd in descriptors:
                os.close(fd)

    def root_exit_code(self) -> int | None:
        state = _wait(self._process, 0)
        if state == _WAIT_TIMEOUT:
            return None
        if state != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = _dword()
        _checked(_exit_code(self._process, ctypes.byref(code)))
        return code.value

    def active_processes(self) -> int:
        accounting = _Accounting()
        with self._job_lock:
            _checked(_query_job(self._job, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                                ctypes.byref(accounting), ctypes.sizeof(accounting), None))
        return accounting.active

    def read(self, stream: str, limit: int) -> bytes | None:
        """Read available bytes, b'' for no new data, None after pipe EOF."""
        fd = self._readers.get(stream)
        if fd is None:
            return None
        available = _dword()
        if _peek_pipe(msvcrt.get_osfhandle(fd), None, 0, None, ctypes.byref(available), None):
            return os.read(fd, min(available.value, limit)) if available.value else b""
        error = ctypes.get_last_error()
        if error not in _PIPE_EOF:
            raise ctypes.WinError(error)
        os.close(self._readers.pop(stream))
        return None

    def duplicate_stdin(self) -> int:
        with self._stdin_lock:
            if self._stdin is None:
                raise OSError("This job has no open stdin pipe")
            return os.dup(self._stdin)

    @property
    def stdin_open(self) -> bool:
        return self._stdin is not None

    def close_stdin(self) -> None:
        with self._stdin_lock:
            if self._stdin is not None:
                os.close(self._stdin)
                self._stdin = None

    def terminate(self) -> None:
        with self._job_lock:
            _checked(_terminate_job(self._job, 1))

    def close_job(self) -> None:
        with self._job_lock:
            if self._job is not None:
                _checked(_close(self._job))
                self._job = None

    def close(self) -> None:
        try:
            self.close_job()
        finally:
            _close(self._process)
            self.close_stdin()
            for fd in self._readers.values():
                os.close(fd)
            self._readers.clear()
