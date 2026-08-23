#!/usr/bin/env python
"""Build the signed first-party System DLC bundle used by source launchers."""

from __future__ import annotations

import json
from pathlib import Path

from engine.dlc.package_builder import write_keypair
from engine.runtime_paths import private_runtime_dir
from scripts.build_system_dlc_bundle import build_system_dlc_bundle


def prepare_dev_system_dlcs() -> tuple[Path, Path]:
    """Return a verified package directory and manifest for this checkout.

    The development publisher key remains in the application-private runtime
    root. It is never committed or accepted by Frozen builds; the generated
    public key is pinned by the returned manifest for this source launch only.
    """

    key_dir = private_runtime_dir("development-system-dlc-key")
    private_key = key_dir / "publisher.pem"
    if not private_key.exists():
        write_keypair(private_key, password=None)

    output_dir = private_runtime_dir("development-system-dlcs")
    manifest = build_system_dlc_bundle(output_dir, private_key)
    return output_dir.resolve(), manifest.resolve()


def main() -> None:
    package_dir, manifest = prepare_dev_system_dlcs()
    print(json.dumps({"package_dir": str(package_dir), "manifest": str(manifest)}))


if __name__ == "__main__":
    main()
