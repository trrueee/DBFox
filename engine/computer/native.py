"""Windows UIA/input adapter. All calls belong to one Host-owned COM thread."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
import ctypes
import hashlib
import os
from pathlib import Path
from typing import Any

from engine.computer.contracts import ActInput, ComputerError, ComputerGrant, ComputerNode, MAX_NODES, Observation, Rect, TargetIdentity
from engine.computer.drivers import CapturedFrame, encode_capture

_BLOCKED_APPS = frozenset({
    "dbfox.exe", "codex.exe", "chatgpt.exe", "consent.exe", "credentialuibroker.exe",
    "logonui.exe", "lockapp.exe", "sechealthui.exe", "securityhealthsystray.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
})
from engine.computer.keys import key_sequence


class NativeDesktop:
    def __init__(self) -> None:
        self._desktop: Any = None
        self._elements: dict[str, dict[str, Any]] = {}

    def _init(self) -> None:
        if self._desktop is None:
            # Per-thread DPI coordinates keep UIA rectangles, captured pixels
            # and physical input in the same space. This changes no OS setting.
            ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            from pywinauto import Desktop
            self._desktop = Desktop(backend="uia")

    @staticmethod
    def _identity(handle: int) -> TargetIdentity:
        import win32api
        import win32gui
        import win32process
        _, pid = win32process.GetWindowThreadProcessId(handle)
        process = win32api.OpenProcess(0x1000, False, pid)
        try:
            from ctypes import wintypes
            query_image = ctypes.WinDLL("kernel32", use_last_error=True).QueryFullProcessImageNameW
            query_image.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
            query_image.restype = wintypes.BOOL
            image = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(image))
            if not query_image(int(process), 0, image, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            executable = image.value
            started = int(win32process.GetProcessTimes(process)["CreationTime"].timestamp() * 1000)
        finally:
            process.Close()
        if pid == os.getpid() or Path(executable).name.lower() in _BLOCKED_APPS:
            raise ComputerError("COMPUTER_TARGET_PROTECTED", "此窗口不开放电脑操作。终端请使用正式命令工具。")
        return TargetIdentity(kind="window", title=win32gui.GetWindowText(handle)[:240],
                              executable=executable, process_id=pid, process_started_at=started,
                              window_handle=format(handle, "x"))

    def targets(self) -> tuple[TargetIdentity, ...]:
        self._init()
        import win32gui
        import pywintypes
        candidates: list[TargetIdentity] = []

        def inspect(handle: int, _unused: object) -> None:
            if len(candidates) >= 64 or not win32gui.IsWindowVisible(handle) or not win32gui.GetWindowText(handle):
                return
            try:
                candidate = self._identity(handle)
            except (ComputerError, OSError, pywintypes.error):
                return
            candidates.append(candidate)

        win32gui.EnumWindows(inspect, None)
        return tuple(candidates)

    def _window(self, target: TargetIdentity) -> Any:
        self._init()
        import win32gui
        handle = int(target.window_handle or "0", 16)
        if not win32gui.IsWindow(handle):
            raise ComputerError("COMPUTER_TARGET_GONE", "共享窗口已关闭，请重新选择。")
        actual = self._identity(handle)
        if (actual.process_id, actual.process_started_at, actual.executable) != (
            target.process_id, target.process_started_at, target.executable,
        ):
            raise ComputerError("COMPUTER_TARGET_CHANGED", "窗口或程序身份已变化，旧共享不可继续使用。")
        foreground = win32gui.GetForegroundWindow()
        if target.include_owned_dialogs and foreground != handle:
            owner = foreground
            for _ in range(12):
                owner = win32gui.GetWindow(owner, 4) if owner else 0  # GW_OWNER
                if owner == handle:
                    dialog = self._identity(foreground)
                    if (dialog.process_id, dialog.process_started_at) == (target.process_id, target.process_started_at):
                        handle = foreground
                    break
        if win32gui.IsIconic(handle):
            raise ComputerError("COMPUTER_TARGET_MINIMIZED", "窗口已最小化，请恢复窗口后重新观察。")
        return self._desktop.window(handle=handle).wrapper_object()

    @staticmethod
    def _bounds(window: Any) -> Rect:
        rect = window.rectangle()
        return Rect(x=rect.left, y=rect.top, width=rect.width(), height=rect.height())

    def capture(self, grant: ComputerGrant, *, remember: bool = True) -> CapturedFrame:
        from PIL import ImageGrab
        window = self._window(grant.target)
        bounds = self._bounds(window)
        if bounds.width <= 0 or bounds.height <= 0:
            raise ComputerError("COMPUTER_CAPTURE_UNAVAILABLE", "窗口没有可观察的内容范围。")
        # Pillow's window capture uses the selected HWND, never a desktop crop
        # that could accidentally include a different overlapping application.
        png, width, height = encode_capture(ImageGrab.grab(window=window.handle))
        pending = deque([(window, 0)])
        nodes: list[ComputerNode] = []
        elements: dict[str, Any] = {}
        visited = 0
        truncated = False
        while pending and visited < 256 and len(nodes) < MAX_NODES:
            element, depth = pending.popleft()
            visited += 1
            try:
                info = element.element_info
                rect = self._bounds(element)
                if not element.is_visible() or rect.width <= 0 or rect.height <= 0:
                    continue
                sensitive = bool(info.element.CurrentIsPassword)
                name = str(info.name or "")[:160]
                role = str(info.control_type or "")[:64]
                value = None
                value_hash = None
                if role == "Edit" and not sensitive:
                    full_value = str(element.get_value())
                    value = full_value[:160]
                    value_hash = hashlib.sha256(full_value.encode("utf-8")).hexdigest()
                if name or role in {"Edit", "Button", "CheckBox", "ComboBox"}:
                    node_id = f"n{len(nodes)}"
                    nodes.append(ComputerNode(id=node_id, role=role, name=name, value=value, value_sha256=value_hash,
                                              bounds=rect, enabled=element.is_enabled(), sensitive=sensitive))
                    elements[node_id] = element
                children = element.children()
                if depth < 16:
                    truncated = truncated or len(children) > 64
                    pending.extend((child, depth + 1) for child in children[:64])
                elif children:
                    truncated = True
            except Exception:
                continue  # A detached element contributes no guessed identity.
        if remember:
            self._elements[grant.id] = elements
        return CapturedFrame(title=window.window_text()[:240], url=None, bounds=bounds,
                             png=png, image_width=width, image_height=height, nodes=tuple(nodes),
                             truncated=truncated or bool(pending), window_handle=format(window.handle, "x"))

    def prepare(self, grant: ComputerGrant, before: Observation, action: ActInput,
                check_cancelled: Callable[[], None]) -> Callable[[], None]:
        import win32gui
        from pywinauto import keyboard, mouse
        window = self._window(grant.target)
        if format(window.handle, "x") != before.window_handle or self._bounds(window) != before.bounds:
            raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "窗口或位置已变化，请重新观察后操作。")
        node = next((node for node in before.nodes if node.id == action.node_id), None)
        element = self._elements.get(grant.id, {}).get(action.node_id or "")
        if action.node_id is not None:
            if node is None or element is None or node.sensitive or not node.enabled:
                raise ComputerError("COMPUTER_ELEMENT_UNAVAILABLE", "元素不可用或属于敏感输入，请重新观察或由用户接管。")
            if self._bounds(element) != node.bounds or str(element.element_info.name or "")[:160] != node.name:
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "元素已变化，请重新观察。")
        sequence = key_sequence(action.key or "") if action.action == "key" else ""
        if action.action == "type_text" and (node is None or node.role != "Edit" or element is None):
            raise ComputerError("COMPUTER_EDIT_REQUIRED", "写入文字需要观察中明确的、非敏感的可编辑元素。", 400)
        if action.action in {"back", "forward", "reload", "new_tab", "select_tab", "close_tab"}:
            raise ComputerError("COMPUTER_ACTION_UNSUPPORTED", "此动作用于受控浏览器。", 400)
        if node:
            point = (node.bounds.x + node.bounds.width // 2, node.bounds.y + node.bounds.height // 2)
        else:
            p = action.point
            point = (before.bounds.x + int((p.x if p else .5) * (before.bounds.width - 1)),
                     before.bounds.y + int((p.y if p else .5) * (before.bounds.height - 1)))

        def perform() -> None:
            check_cancelled()
            current = self._window(grant.target)
            if current.handle != window.handle or self._bounds(current) != before.bounds:
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "目标已变化，未发送输入。")
            if action.action == "focus":
                window.set_focus()
                return
            if win32gui.GetForegroundWindow() != window.handle:
                raise ComputerError("COMPUTER_FOCUS_CHANGED", "目标不在前台。请先批准聚焦，再重新观察。")
            if action.action in {"click", "double_click", "scroll"}:
                hit = win32gui.WindowFromPoint(point)
                if hit != window.handle and not win32gui.IsChild(window.handle, hit):
                    raise ComputerError("COMPUTER_TARGET_OCCLUDED", "输入位置被其他窗口遮挡，未发送输入。")
            check_cancelled()
            if action.action == "type_text":
                assert node is not None and element is not None
                if bool(element.element_info.element.CurrentIsPassword):
                    raise ComputerError("COMPUTER_SENSITIVE_INPUT", "敏感输入需要用户接管。")
                if hashlib.sha256(str(element.get_value()).encode("utf-8")).hexdigest() != node.value_sha256:
                    raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "输入内容已变化，未覆盖用户输入。")
                check_cancelled()
                element.set_edit_text(action.text)
            elif action.action == "key":
                from pywinauto.uia_defines import IUIA
                automation = IUIA()
                focused = automation.iuia.GetFocusedElement()
                if bool(focused.CurrentIsPassword):
                    raise ComputerError("COMPUTER_SENSITIVE_INPUT", "敏感输入需要用户接管。")
                check_cancelled()
                keyboard.send_keys(sequence, pause=0)
            elif action.action == "scroll":
                mouse.scroll(coords=point, wheel_dist=max(1, abs(action.scroll_y) // 120) * (1 if action.scroll_y < 0 else -1))
            else:
                mouse.click(coords=point)
                if action.action == "double_click":
                    check_cancelled()
                    mouse.click(coords=point)
        return perform

    def forget(self, target_id: str) -> None:
        self._elements.pop(target_id, None)
