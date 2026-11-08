"""Cold-sign the complete owner and enroll it through the normal DLC service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import socket
import zipfile
from io import BytesIO

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source


def prepare(directory: Path, *, upgrade: bool = False) -> None:
    source = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.game"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "game.dbfox-dlc"
    service = DlcPackageService(directory / "dlcs")
    if archive.exists() and not upgrade:
        raise ValueError("An existing author runtime must be explicitly reused")
    if upgrade:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", 19230)) != 0, "Stop the task-owned Electron before replacing its package"
        original = json.loads((directory / "package-provenance.json").read_text(encoding="utf-8"))
        (directory / f"game-{original['package_digest']}.dbfox-dlc").write_bytes(archive.read_bytes())
        service.set_desired_enabled("dbfox.game", False)
        service.uninstall("dbfox.game", active_package_digests=frozenset())
    package = build_dlc_package_from_source(source, private_key=Ed25519PrivateKey.generate())
    archive.write_bytes(package.archive_bytes)
    provenance = []
    with zipfile.ZipFile(BytesIO(package.archive_bytes)) as signed:
        for path in sorted((source / "frontend").rglob("*")):
            if path.is_file():
                name = path.relative_to(source).as_posix()
                content = path.read_bytes()
                assert signed.read(name) == content, name
                provenance.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    service.trust_publisher_from_file(archive, expected_package_digest=package.package_digest,
                                    expected_publisher_key_id=package.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled("dbfox.game", True)
    record = {"package_digest": package.package_digest, "publisher_fingerprint": package.publisher_fingerprint,
              "frontend": provenance, "boundary": "complete signed source, normal trust/install/enable lifecycle"}
    (directory / "package-provenance.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"package_digest": package.package_digest, "frontend_files": len(provenance)}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve(), upgrade="--upgrade" in sys.argv)
