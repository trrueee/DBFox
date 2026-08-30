"""Build the signed first-party capability bundle for a Frozen DBFox release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from engine.dlc.package_builder import (
    build_dlc_package,
    collect_payload_files,
    load_private_key,
    read_manifest_template,
)
from engine.dlc.integrity import canonical_json_bytes
from engine.dlc.system_bundle import SystemDlcBundleManifest, SystemDlcPackagePin
from engine.dlc.trust import public_key_to_base64

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DLC_SOURCES = (
    REPOSITORY_ROOT / "dlcs" / "dbfox_data",
    REPOSITORY_ROOT / "dlcs" / "dbfox.workspace",
    REPOSITORY_ROOT / "dlcs" / "dbfox.music",
    REPOSITORY_ROOT / "dlcs" / "dbfox.visualization",
    REPOSITORY_ROOT / "dlcs" / "dbfox.story",
)
SYSTEM_DLC_BUNDLE_INDEX = "system-dlcs.json"
SYSTEM_DLC_DEFAULT_ENABLED = {
    "dbfox.data": True,
    "dbfox.workspace": True,
    "dbfox.music": True,
    "dbfox.visualization": True,
    "dbfox.story": True,
}
_RELEASE_VERSION_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")


def build_system_dlc_bundle(
    output_dir: Path,
    private_key_path: Path,
    *,
    development: bool = False,
) -> Path:
    """Build deterministic signed packages and return the pinned bundle manifest."""

    private_key = load_private_key(private_key_path.resolve(strict=True))
    public_key = public_key_to_base64(private_key.public_key())
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pins: list[SystemDlcPackagePin] = []
    for source_root in SYSTEM_DLC_SOURCES:
        manifest_data = read_manifest_template(source_root)
        payload_files = collect_payload_files(source_root)
        if development:
            manifest_data["version"] = _development_version(
                manifest_data,
                payload_files,
            )
        built = build_dlc_package(
            manifest_data,
            payload_files,
            private_key=private_key,
        )
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
        development=development,
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


def _development_version(
    manifest_data: dict[str, object],
    payload_files: dict[str, bytes],
) -> str:
    """Derive one reproducible prerelease version from mutable source inputs."""

    base_version = manifest_data.get("version")
    if not isinstance(base_version, str) or not _RELEASE_VERSION_PATTERN.fullmatch(
        base_version
    ):
        raise ValueError(
            "Development System DLC templates must declare a release X.Y.Z version"
        )
    source_contract = {
        "manifest": manifest_data,
        "payload_sha256": {
            path: hashlib.sha256(content).hexdigest()
            for path, content in sorted(payload_files.items())
        },
    }
    fingerprint = hashlib.sha256(canonical_json_bytes(source_contract)).hexdigest()[:12]
    return f"{base_version}-dev.{fingerprint}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build signed dbfox.data, dbfox.workspace, dbfox.music, and "
            "dbfox.visualization System DLCs"
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = build_system_dlc_bundle(args.output_dir, args.private_key)
    print(manifest_path)


if __name__ == "__main__":
    main()
