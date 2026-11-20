"""Small data boundary between actual OS/browser drivers and the Host runtime."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from engine.computer.contracts import BrowserTab, ComputerError, ComputerNode, MAX_IMAGE_BYTES, Rect


@dataclass(frozen=True)
class CapturedFrame:
    title: str
    url: str | None
    bounds: Rect
    png: bytes
    image_width: int
    image_height: int
    nodes: tuple[ComputerNode, ...]
    truncated: bool
    window_handle: str | None = None
    notes: tuple[str, ...] = ()
    tabs: tuple[BrowserTab, ...] = ()
    current_tab_id: str | None = None


def encode_capture(image: Image.Image) -> tuple[bytes, int, int]:
    """Bound image size once at the genuine pixel/transport boundary."""
    image = image.convert("RGB")
    image.thumbnail((1280, 900), Image.Resampling.LANCZOS)
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    data = out.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise ComputerError("COMPUTER_CAPTURE_TOO_LARGE", "此画面超出图片预算，请缩小目标窗口后重新观察。")
    return data, image.width, image.height
