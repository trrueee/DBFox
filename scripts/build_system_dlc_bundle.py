"""Build the signed first-party capability bundle for a Frozen DBFox release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.dlc.package_builder import (
    build_dlc_package_from_source,
    load_private_key,
)
from engine.dlc.system_bundle import SystemDlcBundleManifest, SystemDlcPackagePin
from engine.dlc.trust import public_key_to_base64

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DLC_SOURCES = (
    REPOSITORY_ROOT / "dlcs" / "dbfox_data",
    REPOSITORY_ROOT / "dlcs" / "dbfox.workspace",
    REPOSITORY_ROOT / "dlcs" / "dbfox.music",
)
SYSTEM_DLC_BUNDLE_INDEX = "system-dlcs.json"
SYSTEM_DLC_DEFAULT_ENABLED = {
    "dbfox.data": True,
    "dbfox.workspace": True,
    "dbfox.music": True,
}


def build_system_dlc_bundle(
    output_dir: Path,
    private_key_path: Path,
) -> Path:
    """Build deterministic signed packages and return the pinned bundle manifest."""

    private_key = load_private_key(private_key_path.resolve(strict=True))
    public_key = public_key_to_base64(private_key.public_key())
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pins: list[SystemDlcPackagePin] = []
    for source_root in SYSTEM_DLC_SOURCES:
        built = build_dlc_package_from_source(source_root, private_key=private_key)
        filename = f"{built.manifest.id}.dbfox-dlc"
        destination = output_dir / filename
        temporary = output_dir / f".{filename}.tmp"
        temporary.write_bytes(built.archive_bytes)
        temporary.replace(destination)
        pins.append(
            SystemDlcPackagePin(
                dlc_id=built.manifest.id,
                version=built.manifest.version,
                filename=filename,
                package_digest=built.package_digest,
                default_enabled=SYSTEM_DLC_DEFAULT_ENABLED[built.manifest.id],
            )
        )

    manifest = SystemDlcBundleManifest(
        publisher_public_key=public_key,
        packages=tuple(pins),
    )
    manifest_path = output_dir / SYSTEM_DLC_BUNDLE_INDEX
    temporary_manifest = output_dir / f".{SYSTEM_DLC_BUNDLE_INDEX}.tmp"
    temporary_manifest.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build signed dbfox.data, dbfox.workspace, and dbfox.music System DLCs"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = build_system_dlc_bundle(args.output_dir, args.private_key)
    print(manifest_path)


if __name__ == "__main__":
    main()
