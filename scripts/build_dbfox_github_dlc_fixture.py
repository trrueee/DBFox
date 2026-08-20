"""Build a signed test package from the authoritative dbfox.github source tree."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.trust import compute_key_fingerprint, public_key_to_base64
from engine.tests.fixtures.dlc_fixture_builder import build_test_dlc_archive

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


def _payload_files() -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    for directory in ("backend", "frontend"):
        for path in sorted((SOURCE_ROOT / directory).rglob("*")):
            relative = path.relative_to(SOURCE_ROOT)
            if not path.is_file() or "__pycache__" in relative.parts:
                continue
            if directory == "backend" and path.suffix != ".py":
                continue
            if directory == "frontend" and not (
                path.suffix in {".js", ".css"} or path.name.endswith(".d.ts")
            ):
                continue
            payload[relative.as_posix()] = path.read_bytes()
    return payload


def build_dbfox_github_dlc_fixture(output_dir: Path) -> BuiltGithubDlcFixture:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(_TEST_PRIVATE_KEY_SEED)
    manifest = json.loads(
        (SOURCE_ROOT / "manifest.template.json").read_text(encoding="utf-8")
    )
    manifest["publisherKey"] = public_key_to_base64(private_key.public_key())
    archive_bytes = build_test_dlc_archive(
        manifest_data=manifest,
        payload_files=_payload_files(),
        private_key=private_key,
    )
    archive = output_dir / "dbfox.github.dbfox-dlc"
    archive.write_bytes(archive_bytes)
    return BuiltGithubDlcFixture(
        archive=archive,
        package_digest=hashlib.sha256(archive_bytes).hexdigest(),
        publisher_fingerprint=compute_key_fingerprint(private_key.public_key()),
    )
