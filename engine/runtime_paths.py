# -*- coding: utf-8 -*-
"""
DBFox 运行期路径配置模块 (Runtime Paths Module)
--------------------------------------
这个模块负责动态计算、创建和管理 DBFox 在运行期间所需的各种数据目录和文件。
例如，本地 SQLite 数据库、临时缓存、敏感密钥文件等。它保证了跨平台 (Windows, macOS, Linux) 的完美兼容。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 定义应用目录名
APP_DIR_NAME = "DBFox"

# 获取当前项目的根目录
# Python 知识点:
#   - `__file__` 是当前脚本文件的绝对路径。
#   - `Path(__file__)` 将其包装成一个 pathlib.Path 对象，提供了非常强大且面向对象的路径操作方法。
#   - `.resolve()` 解析所有的符号链接，并返回真实绝对路径。
#   - `.parent` 获取该路径的父目录。这里 `.parent.parent` 就是获取当前文件 (engine/runtime_paths.py) 向上两级的目录，即项目根目录。
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _default_runtime_root() -> Path:
    r"""
    根据不同的操作系统获取默认的系统应用数据目录 (Application Data Directory)
    
    Python 知识点:
      - `os.environ.get(key)` 从系统环境变量中读取指定的值。如果不存在，返回 None。
      - `os.name`：如果是 Windows 系统，其值通常为 'nt'。
      - `sys.platform`：如果是 macOS 系统，其值通常为 'darwin'。
      - `Path.home()` 返回当前用户的主目录（即家目录，类似于 Windows 的 C:\Users\Username 或 Linux 的 /home/username）。
      - `Path("...") / "..."` 使用 `/` 运算符拼接路径，这是 pathlib 的核心特性，跨平台时会自动使用正确的路径分隔符（Windows 上是 \，Unix/Mac 上是 /）。
    """
    # 1. 检查是否有用户强制指定的系统环境变量
    override = os.environ.get("DBFOX_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()  # .expanduser() 可以把路径里的 ~ 替换为用户家目录

    # 2. Windows 平台
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")  # 获取 Windows 的 AppData\Roaming 目录
        if appdata:
            return Path(appdata) / APP_DIR_NAME  # 例如 C:\Users\Username\AppData\Roaming\DBFox
            
    # 3. macOS 平台
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
        
    # 4. Linux / 其他 Unix 平台 (遵循 XDG 规范)
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / "dbfox"
        return Path.home() / ".local" / "share" / "dbfox"

    # APPDATA is unavailable only in a broken Windows user profile.  Do not
    # fall back to the repository: it is source-controlled/shared storage and
    # can expose credentials, tokens, metadata, and diagnostics.  Callers may
    # explicitly set DBFOX_RUNTIME_DIR when an alternate private location is
    # required.
    raise OSError("DBFOX private runtime root is unavailable; set DBFOX_RUNTIME_DIR")


def _chmod_private(path: Path, *, is_dir: bool) -> None:
    """
    限制目录或文件仅当前操作系统用户可读写 (安全保护机制)
    
    Python 知识点:
      - `try...except` 结构用于捕获并处理异常。
      - `0o700` 和 `0o600`：以 `0o` 开头代表八进制数字（Octal）。在 Unix/Linux 系统中：
        - `700` 代表目录属主拥有“读、写、执行”全部权限，而其他人没有任何权限。
        - `600` 代表文件属主拥有“读、写”权限，其他人没有任何权限。
      - `path.chmod(permissions)` 修改文件或文件夹权限。
    """
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        # 在 Windows 系统上，POSIX 风格的 chmod 八进制权限不能完美被支持（Windows 使用 ACL 机制）。
        # 这里进行“尽力而为 (Best effort)”的配置即可，即使失败也安全忽略。
        pass


def private_runtime_root() -> Path:
    """Return the single application-owned root for all mutable runtime data.

    Metadata, checkpoints, backups, diagnostics, and transient configuration
    must share this root so a versioned reset can reason about one bounded
    ownership domain.  Source-mode execution intentionally uses the same
    private location as packaged execution; repository directories are never
    an application data store.
    """
    root = _default_runtime_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        _chmod_private(root, is_dir=True)
        probe = root / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return root
    except OSError as exc:
        raise OSError(
            "Unable to initialize DBFOX private runtime root; "
            "set DBFOX_RUNTIME_DIR to an application-owned writable directory"
        ) from exc


def private_runtime_dir(name: str) -> Path:
    """
    安全地创建并返回一个指定名称的私有运行期子目录
    
    Python 知识点:
      - 列表推导和循环 `for root in candidates:` 遍历备选的根目录路径。
      - `path.mkdir(parents=True, exist_ok=True)` 创建文件夹：
        - `parents=True` 表示如果父级文件夹不存在，也会一并自动创建（相当于 `mkdir -p`）。
        - `exist_ok=True` 表示如果文件夹已经存在，则不会抛出“文件夹已存在”的异常。
      - `probe.write_text(...)` 向文件写入字符串。
      - `probe.unlink(missing_ok=True)` 删除文件，`missing_ok=True` 表示如果文件不存在也不报错。
    """
    if not name or Path(name).name != name:
        raise ValueError("Runtime directory name must be one path component")
    path = private_runtime_root() / name
    path.mkdir(parents=True, exist_ok=True)
    _chmod_private(path, is_dir=True)
    probe = path / ".write_test"
    probe.write_text("", encoding="utf-8")
    probe.unlink(missing_ok=True)
    return path


def private_runtime_file(name: str, filename: str) -> Path:
    """
    获取一个私有运行期文件的完整路径 (如 auth/.local_token)
    """
    return private_runtime_dir(name) / filename


def write_private_bytes(path: Path, data: bytes) -> None:
    """
    以最高安全级别 (仅当前用户可读写) 向目标路径写入二进制数据
    
    Python 知识点:
      - `path.write_bytes(data)` 将字节数组一次性写入文件中，并且会自动关闭文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)   # 确保父级目录存在
    _chmod_private(path.parent, is_dir=True)         # 限制父目录访问权限
    path.write_bytes(data)                           # 写入二进制数据
    _chmod_private(path, is_dir=False)               # 限制当前文件访问权限


def write_private_text(path: Path, data: str) -> None:
    """
    以最高安全级别 (仅当前用户可读写) 向目标路径写入文本数据
    
    Python 知识点:
      - `data.encode("utf-8")` 将字符串编码为 UTF-8 格式的字节流（bytes），以便写入。
    """
    write_private_bytes(path, data.encode("utf-8"))

