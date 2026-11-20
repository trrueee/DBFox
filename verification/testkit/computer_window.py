"""Dedicated Win32 controls for actual UIA/input acceptance; no user applications."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    import win32api
    import win32con
    import win32gui
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--title", default="DBFox Computer Fixture")
    args = parser.parse_args()
    controls: dict[str, int] = {}

    def window_proc(handle: int, message: int, wparam: int, lparam: int) -> int:
        if message == win32con.WM_COMMAND and win32api.LOWORD(wparam) == 101:
            value = win32gui.GetWindowText(controls["edit"])
            args.result.write_text(value, encoding="utf-8")
            win32gui.SetWindowText(controls["output"], "Saved: " + value)
            return 0
        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(handle, message, wparam, lparam)

    window_class = win32gui.WNDCLASS()
    window_class.hInstance = win32api.GetModuleHandle(None)
    window_class.lpszClassName = "DBFoxComputerFixture"
    window_class.lpfnWndProc = window_proc
    window_class.hbrBackground = win32con.COLOR_WINDOW + 1
    atom = win32gui.RegisterClass(window_class)
    handle = win32gui.CreateWindowEx(0, atom, args.title, win32con.WS_OVERLAPPEDWINDOW,
        100, 100, 620, 320, 0, 0, window_class.hInstance, None)
    style = win32con.WS_CHILD | win32con.WS_VISIBLE
    win32gui.CreateWindowEx(0, "Static", "Fixture text", style, 24, 24, 180, 24, handle, 0, window_class.hInstance, None)
    controls["edit"] = win32gui.CreateWindowEx(win32con.WS_EX_CLIENTEDGE, "Edit", "", style | win32con.ES_AUTOHSCROLL,
        24, 56, 520, 32, handle, 100, window_class.hInstance, None)
    win32gui.CreateWindowEx(0, "Button", "Save fixture", style | win32con.BS_PUSHBUTTON,
        24, 108, 160, 36, handle, 101, window_class.hInstance, None)
    controls["output"] = win32gui.CreateWindowEx(0, "Static", "Not saved", style, 24, 166, 520, 28, handle, 102, window_class.hInstance, None)
    win32gui.ShowWindow(handle, win32con.SW_SHOW)
    win32gui.UpdateWindow(handle)
    print("DBFOX_COMPUTER_FIXTURE_READY", flush=True)
    win32gui.PumpMessages()


if __name__ == "__main__":
    main()
