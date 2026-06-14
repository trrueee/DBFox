from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
TAURI_ICONS = ROOT / "desktop" / "src-tauri" / "icons"
FAVICON = ROOT / "desktop" / "public" / "favicon.png"


def _rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _assert_transparent_padding(path: Path, min_padding_ratio: float = 0.08) -> None:
    image = _rgba(path)
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()

    assert bbox is not None, f"{path} is fully transparent"

    left, top, right, bottom = bbox
    min_padding = max(1, round(min(image.size) * min_padding_ratio))
    actual_padding = min(left, top, image.width - right, image.height - bottom)

    assert actual_padding >= min_padding, (
        f"{path} alpha bounds {bbox} leave only {actual_padding}px padding; "
        f"expected at least {min_padding}px"
    )
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((image.width - 1, 0)) == 0
    assert alpha.getpixel((0, image.height - 1)) == 0
    assert alpha.getpixel((image.width - 1, image.height - 1)) == 0


def test_tauri_bundle_icons_are_transparent_and_safely_padded() -> None:
    expected_png_sizes = {
        "32x32.png": (32, 32),
        "64x64.png": (64, 64),
        "128x128.png": (128, 128),
        "128x128@2x.png": (256, 256),
        "icon.png": (512, 512),
    }

    for filename, expected_size in expected_png_sizes.items():
        path = TAURI_ICONS / filename
        assert _rgba(path).size == expected_size
        _assert_transparent_padding(path)


def test_windows_ico_contains_common_shell_sizes() -> None:
    icon = Image.open(TAURI_ICONS / "icon.ico")

    assert set(icon.ico.sizes()) >= {
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }


def test_favicon_uses_same_transparent_mark_as_bundle_icon() -> None:
    favicon = _rgba(FAVICON)
    bundle_icon = _rgba(TAURI_ICONS / "32x32.png")

    assert favicon.size == (32, 32)
    _assert_transparent_padding(FAVICON)
    assert ImageChops.difference(favicon, bundle_icon).getbbox() is None
