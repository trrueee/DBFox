from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
ICON_ROOT = DESKTOP_ROOT / "src-tauri" / "icons"
FAVICON = DESKTOP_ROOT / "public" / "favicon.png"
WINDOWS_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
TAURI_PNG_FILES = (
    "32x32.png",
    "64x64.png",
    "128x128.png",
    "128x128@2x.png",
    "icon.png",
)
MIN_VISIBLE_ALPHA = 8
WINDOWS_CONTENT_PADDING_RATIO = 0.0
# Windows may resample any embedded frame for taskbar/titlebar DPI buckets.
# Preserve a small transparent safety margin at every declared shell size while
# keeping at least 87% of the canvas occupied by the mark.
WINDOWS_FRAME_PADDING_RATIO = 0.02


def _clean_invisible_alpha(image: Image.Image) -> Image.Image:
    cleaned = image.copy()
    alpha = cleaned.getchannel("A").point(
        lambda value: 0 if value < MIN_VISIBLE_ALPHA else value,
    )
    cleaned.putalpha(alpha)
    return cleaned


def _windows_shell_source(source: Image.Image) -> Image.Image:
    alpha_bounds = _clean_invisible_alpha(source).getchannel("A").getbbox()
    if alpha_bounds is None:
        raise ValueError("Desktop icon source is fully transparent")

    left, top, right, bottom = alpha_bounds
    content_width = right - left
    content_height = bottom - top
    canvas_size = round(
        max(content_width, content_height) / (1 - 2 * WINDOWS_CONTENT_PADDING_RATIO),
    )
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    crop_left = round(center_x - canvas_size / 2)
    crop_top = round(center_y - canvas_size / 2)
    return source.crop(
        (crop_left, crop_top, crop_left + canvas_size, crop_top + canvas_size),
    )


def _windows_shell_frame(source: Image.Image, size: int) -> Image.Image:
    padding = max(1, math.ceil(size * WINDOWS_FRAME_PADDING_RATIO))
    content_size = size - 2 * padding
    content = source.resize((content_size, content_size), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    frame.alpha_composite(content, (padding, padding))
    return _clean_invisible_alpha(frame)


def main() -> None:
    source_path = ICON_ROOT / "icon.png"
    favicon_source = ICON_ROOT / "32x32.png"
    if not source_path.is_file() or not favicon_source.is_file():
        raise SystemExit("Run `npm run tauri -- icon ...` before finalizing desktop icons.")

    for filename in TAURI_PNG_FILES:
        path = ICON_ROOT / filename
        with Image.open(path) as generated:
            cleaned = _clean_invisible_alpha(generated.convert("RGBA"))
        cleaned.save(path)

    with Image.open(source_path) as source:
        rgba = _windows_shell_source(source.convert("RGBA"))
        frames = [_windows_shell_frame(rgba, size) for size in WINDOWS_ICON_SIZES]
        temporary_icon = ICON_ROOT / "icon.ico.tmp"
        frames[-1].save(
            temporary_icon,
            format="ICO",
            sizes=[(size, size) for size in WINDOWS_ICON_SIZES],
            append_images=frames[:-1],
        )
    temporary_icon.replace(ICON_ROOT / "icon.ico")

    temporary_favicon = FAVICON.with_suffix(".png.tmp")
    shutil.copyfile(favicon_source, temporary_favicon)
    temporary_favicon.replace(FAVICON)


if __name__ == "__main__":
    main()
