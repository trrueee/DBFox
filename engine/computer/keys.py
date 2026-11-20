"""One declared keyboard boundary shared by native and browser adapters."""
from engine.computer.contracts import ComputerError

_KEYS = frozenset({
    "ENTER", "ESC", "TAB", "BACKSPACE", "DELETE", "HOME", "END", "UP", "DOWN",
    "LEFT", "RIGHT", "PGUP", "PGDN", "SPACE", "INSERT", "F1", "F2", "F3", "F4",
    "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
})


def key_sequence(value: str) -> str:
    parts = value.upper().split("+")
    if len(parts) > 4 or any(part not in {"CTRL", "SHIFT", "ALT"} for part in parts[:-1]):
        raise ComputerError("COMPUTER_KEY_UNSUPPORTED", "使用 Ctrl、Shift、Alt 与明确的按键；不支持系统切换快捷键。", 400)
    final, modifiers = parts[-1], set(parts[:-1])
    if final not in _KEYS and not (len(final) == 1 and final.isascii() and final.isalnum()):
        raise ComputerError("COMPUTER_KEY_UNSUPPORTED", "此按键不在允许的按键集合中。", 400)
    if ("CTRL" in modifiers and final in {"C", "V", "X", "ESC"}) or (
        "ALT" in modifiers and final in {"TAB", "ESC"}
    ) or ("SHIFT" in modifiers and final in {"INSERT", "DELETE"}) or (
        {"CTRL", "ALT"}.issubset(modifiers) and final == "DELETE"
    ):
        raise ComputerError("COMPUTER_KEY_UNSUPPORTED", "剪贴板、任务管理和应用切换不通过此目标的键盘入口开放。", 400)
    prefix = "".join({"CTRL": "^", "SHIFT": "+", "ALT": "%"}[part] for part in parts[:-1])
    return prefix + ("{" + final + "}" if final in _KEYS else final.lower())
