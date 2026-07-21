import json
import re
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
TAURI_CONF = ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
TAURI_ICONS = ROOT / "desktop" / "src-tauri" / "icons"
NSIS_HOOKS = ROOT / "desktop" / "src-tauri" / "nsis-hooks.nsh"
WIX_TEMPLATE = ROOT / "desktop" / "src-tauri" / "wix-template.wxs"
FAVICON = ROOT / "desktop" / "public" / "favicon.png"


def _rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _assert_image_transparent_padding(
    image: Image.Image,
    label: str,
    min_padding_ratio: float = 0.08,
) -> None:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()

    assert bbox is not None, f"{label} is fully transparent"

    left, top, right, bottom = bbox
    min_padding = max(1, round(min(image.size) * min_padding_ratio))
    actual_padding = min(left, top, image.width - right, image.height - bottom)

    assert actual_padding >= min_padding, (
        f"{label} alpha bounds {bbox} leave only {actual_padding}px padding; "
        f"expected at least {min_padding}px"
    )
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((image.width - 1, 0)) == 0
    assert alpha.getpixel((0, image.height - 1)) == 0
    assert alpha.getpixel((image.width - 1, image.height - 1)) == 0


def _assert_transparent_padding(path: Path, min_padding_ratio: float = 0.08) -> None:
    _assert_image_transparent_padding(_rgba(path), str(path), min_padding_ratio)


def _border_has_opaque_white_pixel(image: Image.Image) -> bool:
    def is_opaque_white(pixel: tuple[int, int, int, int]) -> bool:
        r, g, b, alpha = pixel
        return alpha > 0 and r > 240 and g > 240 and b > 240

    for x in range(image.width):
        if is_opaque_white(image.getpixel((x, 0))):
            return True
        if is_opaque_white(image.getpixel((x, image.height - 1))):
            return True

    for y in range(image.height):
        if is_opaque_white(image.getpixel((0, y))):
            return True
        if is_opaque_white(image.getpixel((image.width - 1, y))):
            return True

    return False


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
    expected_sizes = {
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }

    with Image.open(TAURI_ICONS / "icon.ico") as icon:
        assert set(icon.ico.sizes()) >= expected_sizes

        for size in expected_sizes:
            frame = icon.ico.getimage(size).convert("RGBA")
            label = f"icon.ico {size[0]}x{size[1]}"

            _assert_image_transparent_padding(frame, label, min_padding_ratio=0.16)
            assert not _border_has_opaque_white_pixel(frame), (
                f"{label} has opaque white pixels on the canvas border"
            )


def test_favicon_uses_same_transparent_mark_as_bundle_icon() -> None:
    favicon = _rgba(FAVICON)
    bundle_icon = _rgba(TAURI_ICONS / "32x32.png")

    assert favicon.size == (32, 32)
    _assert_transparent_padding(FAVICON)
    assert ImageChops.difference(favicon, bundle_icon).getbbox() is None


def test_windows_installer_uses_bundled_icon_for_distribution_shortcuts() -> None:
    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    bundle = config["bundle"]
    windows = bundle["windows"]
    nsis = windows["nsis"]
    wix = windows["wix"]

    assert bundle["targets"] == "all"
    assert bundle["resources"]["icons/icon.ico"] == "dbfox-icon.ico"
    assert nsis["installerIcon"] == "icons/icon.ico"
    assert nsis["uninstallerIcon"] == "icons/icon.ico"
    assert nsis["installerHooks"] == "nsis-hooks.nsh"
    assert wix["template"] == "wix-template.wxs"

    hooks = NSIS_HOOKS.read_text(encoding="utf-8")
    assert "$INSTDIR\\dbfox-icon.ico" in hooks
    assert "$DESKTOP\\${PRODUCTNAME}.lnk" in hooks
    assert "$SMPROGRAMS\\${PRODUCTNAME}.lnk" in hooks
    assert "CreateShortcut" in hooks
    assert "SHChangeNotify" in hooks
    assert "!macro NSIS_HOOK_PREINSTALL" in hooks
    assert "!macro NSIS_HOOK_PREUNINSTALL" in hooks
    assert 'KillProcessCurrentUser "dbfox-engine.exe"' in hooks
    assert 'KillProcess "dbfox-engine.exe"' in hooks

    wix_template = WIX_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(
        r'<Shortcut\s+Id="ApplicationDesktopShortcut"[^>]*Icon="ProductIcon"',
        wix_template,
        re.DOTALL,
    )
    assert re.search(
        r'<Shortcut\s+Id="ApplicationStartMenuShortcut"[^>]*Icon="ProductIcon"',
        wix_template,
        re.DOTALL,
    )
