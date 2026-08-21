"""Build a signed test package from the authoritative dbfox.github source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.package_builder import build_dlc_package_from_source

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "dlcs" / "dbfox.github"
_TEST_PRIVATE_KEY_SEED = hashlib.sha256(
    b"DBFox dbfox.github DLC conformance fixture; never use for production signing"
).digest()


@dataclass(frozen=True)
class BuiltGithubDlcFixture:
    archive: Path
    package_digest: str
    publisher_fingerprint: str


def build_dbfox_github_dlc_fixture(output_dir: Path) -> BuiltGithubDlcFixture:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(_TEST_PRIVATE_KEY_SEED)
    built = build_dlc_package_from_source(
        SOURCE_ROOT,
        private_key=private_key,
    )
    archive = output_dir / "dbfox.github.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    return BuiltGithubDlcFixture(
        archive=archive,
        package_digest=built.package_digest,
        publisher_fingerprint=built.publisher_fingerprint or "",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the signed dbfox.github conformance fixture"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    built = build_dbfox_github_dlc_fixture(args.output_dir)
    print(
        json.dumps(
            {
                "archive": str(built.archive),
                "package_digest": built.package_digest,
                "publisher_fingerprint": built.publisher_fingerprint,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
