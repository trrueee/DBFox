"""Command-line developer kit for DBFox DLC projects."""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

from engine.dlc.manifest import DlcManifest
from engine.dlc.package_builder import (
    MANIFEST_TEMPLATE_NAME,
    PUBLISHER_KEY_PLACEHOLDER,
    build_dlc_package_from_source,
    load_private_key,
    load_public_key,
    sign_unsigned_archive,
    write_keypair,
)
from engine.dlc.trust import DlcTrustStore, public_key_to_base64
from engine.dlc.verifier import DlcPackageVerifier, VerifiedDlcPackage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbfox-dlc",
        description="Build and verify DBFox DLC packages without touching the installed registry.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a minimal DLC source tree")
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument("--id", required=True, dest="dlc_id")
    init_parser.add_argument("--publisher", required=True)
    init_parser.add_argument("--display-name")
    init_parser.add_argument("--generate-key", type=Path, metavar="PRIVATE_KEY_PEM")
    init_parser.add_argument("--key-password-env", metavar="ENV_NAME")
    init_parser.add_argument(
        "--unencrypted-key",
        action="store_true",
        help="Explicitly generate an unencrypted private key (intended for isolated CI fixtures)",
    )
    init_parser.set_defaults(handler=_command_init)

    build_parser_ = subparsers.add_parser(
        "build", help="Create a deterministic signed or unsigned package"
    )
    build_parser_.add_argument("source", type=Path)
    build_parser_.add_argument("--output", "-o", type=Path, required=True)
    build_parser_.add_argument("--private-key", type=Path)
    build_parser_.add_argument("--public-key", type=Path)
    build_parser_.add_argument("--key-password-env", metavar="ENV_NAME")
    build_parser_.add_argument(
        "--unsigned",
        action="store_true",
        help="Produce an intermediate package for an offline signing step",
    )
    build_parser_.set_defaults(handler=_command_build)

    sign_parser = subparsers.add_parser(
        "sign", help="Sign a deterministic unsigned package with an Ed25519 key"
    )
    sign_parser.add_argument("archive", type=Path)
    sign_parser.add_argument("--private-key", type=Path, required=True)
    sign_parser.add_argument("--output", "-o", type=Path, required=True)
    sign_parser.add_argument("--key-password-env", metavar="ENV_NAME")
    sign_parser.set_defaults(handler=_command_sign)

    test_parser = subparsers.add_parser(
        "test", help="Run host-equivalent verification and non-executing syntax checks"
    )
    test_parser.add_argument("archive", type=Path)
    test_parser.set_defaults(handler=_command_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"dbfox-dlc: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # DlcError intentionally remains a typed engine exception rather than a
        # CLI-specific mirror.  Keep command output concise while preserving its
        # stable code for automation.
        error_code = getattr(exc, "code", None)
        error_value = getattr(error_code, "value", None)
        prefix = f"{error_value}: " if error_value is not None else ""
        print(f"dbfox-dlc: {prefix}{exc}", file=sys.stderr)
        return 1


def _command_init(args: argparse.Namespace) -> int:
    source_root: Path = args.path.resolve()
    manifest_path = source_root / MANIFEST_TEMPLATE_NAME
    if manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite '{manifest_path}'")

    publisher_key = PUBLISHER_KEY_PLACEHOLDER
    key_summary: dict[str, str] = {}
    if args.generate_key is not None:
        password = _new_key_password(args)
        public_path, fingerprint = write_keypair(args.generate_key, password=password)
        publisher_key = public_key_to_base64(load_public_key(public_path))
        key_summary = {
            "private_key": str(args.generate_key.resolve()),
            "public_key": str(public_path),
            "publisher_fingerprint": fingerprint,
        }

    source_root.mkdir(parents=True, exist_ok=True)
    backend = source_root / "backend"
    frontend = source_root / "frontend"
    backend.mkdir(exist_ok=True)
    frontend.mkdir(exist_ok=True)
    manifest = {
        "manifestSchemaVersion": 2,
        "id": args.dlc_id,
        "version": "0.1.0",
        "displayName": args.display_name or args.dlc_id,
        "publisher": args.publisher,
        "publisherKey": publisher_key,
        "description": "",
        "extensionApiVersion": "1",
        "requiresDbfox": ">=1.0.0",
        "entrypoints": {
            "backend": "backend/entry.py",
            "frontend": "frontend/index.js",
        },
        "permissions": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_new_text(
        backend / "entry.py",
        '"""DBFox DLC backend entrypoint."""\n\n\ndef register(host) -> None:\n    pass\n',
    )
    _write_new_text(
        frontend / "index.js",
        "export function register(host) {\n  void host;\n}\n",
    )
    print(json.dumps({"source": str(source_root), **key_summary}, sort_keys=True))
    return 0


def _write_new_text(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _new_key_password(args: argparse.Namespace) -> bytes | None:
    if args.unencrypted_key:
        if args.key_password_env:
            raise ValueError("--unencrypted-key cannot be combined with --key-password-env")
        return None
    if args.key_password_env:
        value = os.environ.get(args.key_password_env)
        if not value:
            raise ValueError(f"Key password environment variable '{args.key_password_env}' is empty")
        return value.encode("utf-8")
    first = getpass.getpass("New publisher key password: ").encode("utf-8")
    second = getpass.getpass("Confirm publisher key password: ").encode("utf-8")
    if not first or first != second:
        raise ValueError("Publisher key passwords are empty or do not match")
    return first


def _read_private_key(path: Path, password_env: str | None):
    password = None
    if password_env:
        raw_password = os.environ.get(password_env)
        if not raw_password:
            raise ValueError(f"Key password environment variable '{password_env}' is empty")
        password = raw_password.encode("utf-8")
    try:
        return load_private_key(path, password=password)
    except ValueError:
        if password is not None or not sys.stdin.isatty():
            raise
        prompted = getpass.getpass("Publisher key password: ").encode("utf-8")
        return load_private_key(path, password=prompted)


def _command_build(args: argparse.Namespace) -> int:
    if args.unsigned and args.private_key:
        raise ValueError("--unsigned cannot be combined with --private-key")
    if not args.unsigned and args.private_key is None:
        raise ValueError("Signed builds require --private-key; use --unsigned for offline signing")
    private_key = (
        _read_private_key(args.private_key, args.key_password_env)
        if args.private_key is not None
        else None
    )
    public_key = load_public_key(args.public_key) if args.public_key is not None else None
    built = build_dlc_package_from_source(
        args.source,
        private_key=private_key,
        public_key=public_key,
    )
    _write_archive_output(args.output, built.archive_bytes)
    print(
        json.dumps(
            {
                "archive": str(args.output.resolve()),
                "dlc_id": built.manifest.id,
                "package_digest": built.package_digest,
                "publisher_fingerprint": built.publisher_fingerprint,
                "signed": private_key is not None,
            },
            sort_keys=True,
        )
    )
    return 0


def _command_sign(args: argparse.Namespace) -> int:
    private_key = _read_private_key(args.private_key, args.key_password_env)
    built = sign_unsigned_archive(args.archive.read_bytes(), private_key)
    _write_archive_output(args.output, built.archive_bytes)
    print(
        json.dumps(
            {
                "archive": str(args.output.resolve()),
                "dlc_id": built.manifest.id,
                "package_digest": built.package_digest,
                "publisher_fingerprint": built.publisher_fingerprint,
                "signed": True,
            },
            sort_keys=True,
        )
    )
    return 0


def _write_archive_output(path: Path, content: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite '{path}'")
    with path.open("xb") as handle:
        handle.write(content)


def _command_test(args: argparse.Namespace) -> int:
    archive_path: Path = args.archive.resolve()
    with tempfile.TemporaryDirectory(prefix="dbfox-dlc-test-") as temporary:
        isolated_archive = Path(temporary) / archive_path.name
        shutil.copyfile(archive_path, isolated_archive)
        verified = _verify_with_embedded_key(isolated_archive)
        python_files, javascript_files = _syntax_check_payload(verified)
    print(
        json.dumps(
            {
                "dlc_id": verified.manifest.id,
                "package_digest": verified.package_digest,
                "publisher_fingerprint": verified.publisher_key_id,
                "python_files_checked": python_files,
                "javascript_files_checked": javascript_files,
                "registry_modified": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _verify_with_embedded_key(archive_path: Path) -> VerifiedDlcPackage:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            manifest = DlcManifest.from_bytes(archive.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"Invalid DLC archive: {exc}") from exc
    if manifest.publisher_key is None:
        raise ValueError("Conformance testing requires a v2 package with an embedded publisher key")
    trust_store = DlcTrustStore({"embedded": manifest.publisher_key})
    return DlcPackageVerifier(trust_store).verify_archive_file(archive_path)


def _syntax_check_payload(verified: VerifiedDlcPackage) -> tuple[int, int]:
    python_count = 0
    javascript_count = 0
    node_path = shutil.which("node")
    with zipfile.ZipFile(io.BytesIO(verified.raw_archive_bytes)) as archive:
        for path in sorted(verified.integrity.entries):
            content = archive.read(path)
            if path.endswith(".py"):
                compile(content, path, "exec", dont_inherit=True)
                python_count += 1
            elif path.endswith((".js", ".mjs")):
                if node_path is None:
                    raise RuntimeError("Node.js is required to syntax-check frontend DLC files")
                result = subprocess.run(
                    [node_path, "--input-type=module", "--check"],
                    input=content,
                    capture_output=True,
                    check=False,
                    timeout=15,
                )
                if result.returncode != 0:
                    error = result.stderr.decode("utf-8", errors="replace").strip()
                    raise ValueError(f"JavaScript syntax check failed for '{path}': {error}")
                javascript_count += 1
    return python_count, javascript_count


if __name__ == "__main__":
    raise SystemExit(main())
