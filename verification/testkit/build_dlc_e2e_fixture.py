"""Build signed acme.echo archives for the packaged DLC lifecycle contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.package_builder import build_dlc_package
from verification.testkit.dlc_fixture_builder import build_test_dlc_archive

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SOURCE_ROOT = REPOSITORY_ROOT / "test-fixtures" / "dlc" / "acme.echo"
_FIXTURE_PRIVATE_KEY_SEED = hashlib.sha256(
    b"DBFox acme.echo packaged E2E fixture key; test use only"
).digest()


@dataclass(frozen=True)
class BuiltDlcE2eFixtures:
    valid_archive: Path
    update_archive: Path
    tampered_archive: Path
    package_digest: str
    update_package_digest: str
    publisher_fingerprint: str


def build_dlc_e2e_fixtures(output_dir: Path) -> BuiltDlcE2eFixtures:
    """Build the valid and payload-tampered single-file fixture archives."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
        _FIXTURE_PRIVATE_KEY_SEED
    )
    manifest = json.loads(
        (FIXTURE_SOURCE_ROOT / "manifest.template.json").read_text(encoding="utf-8")
    )
    payload_files = {
        "backend/__init__.py": (
            FIXTURE_SOURCE_ROOT / "backend" / "__init__.py"
        ).read_bytes(),
        "backend/entry.py": (
            FIXTURE_SOURCE_ROOT / "backend" / "entry.py"
        ).read_bytes(),
        "frontend/index.js": (
            FIXTURE_SOURCE_ROOT / "frontend" / "index.js"
        ).read_bytes(),
    }

    valid = build_dlc_package(
        manifest,
        payload_files,
        private_key=private_key,
    )
    update_manifest = {**manifest, "version": "2.0.0"}
    update = build_dlc_package(
        update_manifest,
        payload_files,
        private_key=private_key,
    )
    manifest["publisherKey"] = valid.manifest.publisher_key
    tampered_bytes = build_test_dlc_archive(
        manifest_data=manifest,
        payload_files=payload_files,
        private_key=private_key,
        corrupt_payload_hash="backend/entry.py",
    )
    valid_archive = output_dir / "acme.echo.dbfox-dlc"
    update_archive = output_dir / "acme.echo-2.0.0.dbfox-dlc"
    tampered_archive = output_dir / "acme.echo-tampered.dbfox-dlc"
    valid_archive.write_bytes(valid.archive_bytes)
    update_archive.write_bytes(update.archive_bytes)
    tampered_archive.write_bytes(tampered_bytes)

    return BuiltDlcE2eFixtures(
        valid_archive=valid_archive,
        update_archive=update_archive,
        tampered_archive=tampered_archive,
        package_digest=valid.package_digest,
        update_package_digest=update.package_digest,
        publisher_fingerprint=valid.publisher_fingerprint or "",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    built = build_dlc_e2e_fixtures(args.output_dir)
    print(
        json.dumps(
            {
                "valid_archive": str(built.valid_archive),
                "update_archive": str(built.update_archive),
                "tampered_archive": str(built.tampered_archive),
                "package_digest": built.package_digest,
                "update_package_digest": built.update_package_digest,
                "publisher_fingerprint": built.publisher_fingerprint,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
