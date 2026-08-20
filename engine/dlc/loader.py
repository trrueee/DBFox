"""Production backend loader for Runtime DLCs with isolated namespaces and pre-execution verification."""

from __future__ import annotations

import base64
import hashlib
import importlib.machinery
import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from engine.dlc.api import BackendExtensionHost
from engine.dlc.compat import check_dlc_compatibility
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.integrity import (
    DlcIntegrity,
    build_signed_message_bytes,
    canonical_json_bytes,
)
from engine.dlc.manifest import DlcManifest
from engine.dlc.trust import (
    DlcTrustStatus,
    DlcTrustStore,
    compute_key_fingerprint,
    public_key_from_base64,
)



_ENTRYPOINT_PATTERN = re.compile(r"^(?:backend/)?(?P<module>[a-zA-Z0-9_./-]+?)(?:\.py)?(?::(?P<func>[a-zA-Z0-9_]+))?$")


def derive_dlc_namespace(dlc_id: str, package_digest: str) -> str:
    """Compute the unique top-level module namespace for a DLC package."""
    safe_id = re.sub(r"[^a-zA-Z0-9_]", "_", dlc_id).strip("_")
    digest_prefix = package_digest[:12].lower()
    return f"_dbfox_dlc_{safe_id}_{digest_prefix}"


def purge_dlc_namespace(namespace: str) -> None:
    """Purge all modules belonging to a DLC namespace from sys.modules."""
    to_remove = [k for k in sys.modules if k == namespace or k.startswith(f"{namespace}.")]
    for k in to_remove:
        sys.modules.pop(k, None)


class _DlcNamespaceFinder:
    """MetaPathFinder that resolves submodules for a specific DLC namespace from its backend directory."""

    def __init__(self, namespace: str, backend_dir: Path) -> None:
        self.namespace = namespace
        self.backend_dir = backend_dir

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not (fullname == self.namespace or fullname.startswith(f"{self.namespace}.")):
            return None

        if fullname == self.namespace:
            init_file = self.backend_dir / "__init__.py"
            if init_file.is_file():
                spec = importlib.util.spec_from_file_location(
                    fullname,
                    init_file,
                    submodule_search_locations=[str(self.backend_dir)],
                )
            else:
                spec = importlib.machinery.ModuleSpec(
                    fullname,
                    None,
                    is_package=True,
                )
                spec.submodule_search_locations = [str(self.backend_dir)]
            return spec

        # Resolve submodules
        sub_rel = fullname[len(self.namespace) + 1 :].replace(".", "/")
        py_file = self.backend_dir / f"{sub_rel}.py"
        if py_file.is_file():
            return importlib.util.spec_from_file_location(fullname, py_file)

        pkg_dir = self.backend_dir / sub_rel
        pkg_init = pkg_dir / "__init__.py"
        if pkg_init.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                pkg_init,
                submodule_search_locations=[str(pkg_dir)],
            )

        return None


def reverify_installed_package(
    dlc_id: str,
    selected_digest: str,
    storage_root: Path,
    trust_store: DlcTrustStore,
    *,
    developer_mode: bool = False,
) -> tuple[DlcManifest, Path, DlcTrustStatus, str | None]:
    """Re-verify an installed DLC package directory before runtime activation.

    Enforces:
    1. Package directory exists at content-addressed path.
    2. manifest.json parses and manifest.id matches dlc_id.
    3. integrity.json exists and all listed payload files exist with matching SHA256.
    4. Ed25519 signature is authentic against trust store (or Developer Mode).
    5. DBFox version and Extension API version are compatible.
    """
    package_dir = storage_root / "packages" / f"sha256-{selected_digest}"
    if not package_dir.is_dir():
        raise DlcError(
            DlcErrorCode.PACKAGE_MISSING,
            f"Package directory not found for DLC '{dlc_id}' at {package_dir}",
        )

    manifest_file = package_dir / "manifest.json"
    integrity_file = package_dir / "integrity.json"
    signature_file = package_dir / "signature.sig"

    if not manifest_file.is_file() or not integrity_file.is_file():
        raise DlcError(
            DlcErrorCode.PACKAGE_TAMPERED,
            f"Control files missing in package directory {package_dir}",
        )

    try:
        manifest_bytes = manifest_file.read_bytes()
        manifest = DlcManifest.from_bytes(manifest_bytes)
    except Exception as exc:
        raise DlcError(
            DlcErrorCode.PACKAGE_TAMPERED,
            f"Failed to parse manifest.json for DLC '{dlc_id}': {exc}",
        ) from exc

    if manifest.id != dlc_id:
        raise DlcError(
            DlcErrorCode.PACKAGE_TAMPERED,
            f"Manifest ID '{manifest.id}' does not match registered DLC ID '{dlc_id}'",
        )

    try:
        integrity_bytes = integrity_file.read_bytes()
        integrity = DlcIntegrity.from_bytes(integrity_bytes)
    except Exception as exc:
        raise DlcError(
            DlcErrorCode.PACKAGE_TAMPERED,
            f"Failed to parse integrity.json for DLC '{dlc_id}': {exc}",
        ) from exc

    # Re-verify payload hashes
    for rel_path, expected_digest in integrity.entries.items():
        file_path = package_dir / rel_path
        if not file_path.is_file():
            raise DlcError(
                DlcErrorCode.PACKAGE_TAMPERED,
                f"Payload file '{rel_path}' missing from package {package_dir}",
            )
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                hasher.update(chunk)
        actual_digest = hasher.hexdigest().lower()
        if actual_digest != expected_digest.lower():
            raise DlcError(
                DlcErrorCode.PACKAGE_TAMPERED,
                f"Payload file '{rel_path}' hash mismatch: expected {expected_digest}, got {actual_digest}",
            )

    # Re-verify signature & trust
    canonical_manifest = canonical_json_bytes(manifest.model_dump(by_alias=True, exclude_none=True))
    signed_payload = build_signed_message_bytes(canonical_manifest, integrity.canonical_bytes())

    trust_status = DlcTrustStatus.UNTRUSTED
    key_fingerprint: str | None = None

    if signature_file.is_file():
        sig_b64 = signature_file.read_text("ascii").strip()
        try:
            sig_bytes = base64.b64decode(sig_b64)
        except Exception as exc:
            raise DlcError(
                DlcErrorCode.INVALID_SIGNATURE,
                f"Invalid base64 signature in {signature_file}: {exc}",
            ) from exc

        # Try verifying against trust store
        verified = False
        for trusted_key_b64 in trust_store.list_trusted_keys():
            try:
                pub_key = public_key_from_base64(trusted_key_b64)
                pub_key.verify(sig_bytes, signed_payload)
                trust_status = DlcTrustStatus.TRUSTED_SIGNED
                key_fingerprint = compute_key_fingerprint(pub_key)
                verified = True
                break
            except Exception:
                continue


        if not verified:
            if developer_mode:
                trust_status = DlcTrustStatus.DEVELOPER_SIGNED
            else:

                raise DlcError(
                    DlcErrorCode.UNTRUSTED_PUBLISHER,
                    f"Signature on package '{dlc_id}' is not trusted by current trust store",
                )
    else:
        if not developer_mode:
            raise DlcError(
                DlcErrorCode.SIGNATURE_REQUIRED,
                f"Unsigned package '{dlc_id}' rejected in production mode",
            )
        trust_status = DlcTrustStatus.DEVELOPER_UNSIGNED

    # Check compatibility
    check_dlc_compatibility(
        manifest.manifest_schema_version,
        manifest.extension_api_version,
        manifest.requires_dbfox,
    )


    return manifest, package_dir, trust_status, key_fingerprint


def load_dlc_backend(
    package_root: Path,
    manifest: DlcManifest,
    package_digest: str,
) -> Callable[[BackendExtensionHost], None]:
    """Load the backend entrypoint of a verified DLC into an isolated module namespace."""
    if not manifest.entrypoints.backend:
        raise DlcError(
            DlcErrorCode.BACKEND_ENTRYPOINT_INVALID,
            f"DLC '{manifest.id}' does not declare a backend entrypoint",
        )

    backend_entry = manifest.entrypoints.backend.strip()
    m = _ENTRYPOINT_PATTERN.match(backend_entry)
    if not m:
        raise DlcError(
            DlcErrorCode.BACKEND_ENTRYPOINT_INVALID,
            f"Invalid backend entrypoint format '{backend_entry}'. Expected 'backend/entry.py' or 'entry:register'",
        )

    module_rel = m.group("module").replace("/", ".").strip(".")
    func_name = m.group("func") or "register"

    backend_dir = package_root / "backend"
    if not backend_dir.is_dir():
        raise DlcError(
            DlcErrorCode.BACKEND_ENTRYPOINT_INVALID,
            f"Backend directory '{backend_dir}' does not exist",
        )

    namespace = derive_dlc_namespace(manifest.id, package_digest)
    finder = _DlcNamespaceFinder(namespace, backend_dir)

    # Register custom finder at the front of sys.meta_path
    sys.meta_path.insert(0, finder)
    try:
        full_module_name = f"{namespace}.{module_rel}" if module_rel != "backend" and module_rel != "entry" and not module_rel.startswith("entry") else f"{namespace}.entry"
        # If entrypoint is "backend/entry.py", module_rel is "entry"
        if module_rel in ("backend/entry", "entry", "backend.entry"):
            full_module_name = f"{namespace}.entry"
        else:
            full_module_name = f"{namespace}.{module_rel}"

        try:
            entry_mod = importlib.import_module(full_module_name)
        except Exception as exc:
            purge_dlc_namespace(namespace)
            raise DlcError(
                DlcErrorCode.BACKEND_IMPORT_FAILED,
                f"Failed to import backend module '{full_module_name}' for DLC '{manifest.id}': {exc}",
            ) from exc

        register_func = getattr(entry_mod, func_name, None)
        if register_func is None or not callable(register_func):
            purge_dlc_namespace(namespace)
            raise DlcError(
                DlcErrorCode.BACKEND_ENTRYPOINT_INVALID,
                f"Backend entrypoint '{full_module_name}:{func_name}' not found or not callable in DLC '{manifest.id}'",
            )

        return register_func
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
