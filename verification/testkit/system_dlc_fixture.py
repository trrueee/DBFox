"""Isolated first-party System DLC bundle built through production packaging code."""

from __future__ import annotations

from pathlib import Path


def build_isolated_system_dlc_bundle(root: Path) -> tuple[Path, Path]:
    """Build the signed checkout bundle without touching the user's app runtime."""

    from engine.dlc.package_builder import write_keypair
    from scripts.build_system_dlc_bundle import build_system_dlc_bundle

    root.mkdir(parents=True, exist_ok=False)
    private_key = root / "publisher.pem"
    write_keypair(private_key, password=None)
    output_dir = root / "packages"
    manifest = build_system_dlc_bundle(output_dir, private_key)
    return output_dir.resolve(), manifest.resolve()
