"""Local-authenticated DLC package lifecycle and desired/active projection API."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path as PathParameter, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.registry import InstalledDlcRecord
from engine.dlc.service import DlcPackageService
from engine.dlc.snapshot import RuntimeContributionSnapshot
from engine.dlc.trust import DlcTrustStatus
from engine.runtime_composition import get_active_runtime_snapshot
from engine.runtime_paths import private_runtime_dir


router = APIRouter(prefix="/dlcs", tags=["dlc_lifecycle"])


class DlcLifecycleState(StrEnum):
    INSTALLED_DISABLED = "installed_disabled"
    ENABLE_PENDING_RESTART = "enable_pending_restart"
    ACTIVE = "active"
    DISABLE_PENDING_RESTART = "disable_pending_restart"
    ACTIVATION_FAILED = "activation_failed"


class DlcRestartState(StrEnum):
    NONE = "none"
    REQUIRED = "required"
    FAILED = "failed"


class _ArchivePathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    archive_path: str = Field(min_length=1, max_length=4096)

    @field_validator("archive_path")
    @classmethod
    def validate_archive_path(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("archive_path must be absolute")
        if not value.casefold().endswith(".dbfox-dlc"):
            raise ValueError("archive_path must identify a .dbfox-dlc file")
        return value


class DlcPackageInspectRequest(_ArchivePathRequest):
    pass


class DlcPublisherTrustRequest(_ArchivePathRequest):
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publisher_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class DlcInstallRequest(_ArchivePathRequest):
    pass


class DlcPackageInspection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    version: str
    display_name: str
    description: str
    publisher: str
    publisher_fingerprint: str
    package_digest: str
    trust_status: DlcTrustStatus
    trust_required: bool
    permissions: list[str]
    backend_entrypoint_present: bool
    frontend_entrypoint_present: bool


class DlcPublisherTrustResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    publisher_fingerprint: str
    trusted: bool = True


class DlcActivationFailureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class DlcInstalledVersionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    installed_at: str
    selected: bool
    active: bool
    pending: bool
    removable: bool


class DlcLifecycleItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    version: str
    display_name: str
    description: str
    publisher: str
    publisher_fingerprint: str | None
    installed_versions: list[DlcInstalledVersionItem]
    selected_digest: str
    active_digest: str | None
    desired_enabled: bool
    active: bool
    state: DlcLifecycleState
    restart_state: DlcRestartState
    trust_status: str
    permissions: list[str]
    backend_entrypoint_present: bool
    frontend_entrypoint_present: bool
    activation_failure: DlcActivationFailureResponse | None = None


class DlcListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    dlcs: list[DlcLifecycleItem]


class DlcUninstallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    package_digest: str
    package_digests: list[str]
    executable_bytes_removed: bool
    data_retained: bool


class DlcVersionRemovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    package_digest: str
    executable_bytes_removed: bool


_BAD_PACKAGE_CODES = frozenset(
    {
        DlcErrorCode.INVALID_ARCHIVE,
        DlcErrorCode.PACKAGE_TOO_LARGE,
        DlcErrorCode.EXTRACTED_TOO_LARGE,
        DlcErrorCode.TOO_MANY_FILES,
        DlcErrorCode.SINGLE_FILE_TOO_LARGE,
        DlcErrorCode.PATH_TOO_LONG,
        DlcErrorCode.UNSAFE_PATH,
        DlcErrorCode.DUPLICATE_PATH,
        DlcErrorCode.CASE_COLLISION,
        DlcErrorCode.UNLISTED_FILE,
        DlcErrorCode.MISSING_FILE,
        DlcErrorCode.INVALID_MANIFEST,
        DlcErrorCode.INVALID_INTEGRITY,
        DlcErrorCode.HASH_MISMATCH,
        DlcErrorCode.SIGNATURE_REQUIRED,
        DlcErrorCode.INVALID_SIGNATURE,
        DlcErrorCode.PUBLISHER_KEY_MISMATCH,
        DlcErrorCode.INCOMPATIBLE_SCHEMA,
        DlcErrorCode.INCOMPATIBLE_EXTENSION_API,
        DlcErrorCode.INCOMPATIBLE_DBFOX_VERSION,
        DlcErrorCode.NATIVE_EXTENSION_NOT_ALLOWED,
        DlcErrorCode.PACKAGE_TAMPERED,
    }
)
_CONFLICT_CODES = frozenset(
    {
        DlcErrorCode.TRUST_REQUIRED,
        DlcErrorCode.ALREADY_INSTALLED,
        DlcErrorCode.CONFLICTING_DIGEST,
        DlcErrorCode.DLC_DISABLE_REQUIRED,
        DlcErrorCode.DLC_ACTIVE,
        DlcErrorCode.DLC_VERSION_SELECTED,
        DlcErrorCode.DLC_VERSION_ACTIVE,
        DlcErrorCode.DLC_VERSION_LIMIT_REACHED,
    }
)
_STORAGE_CODES = frozenset(
    {
        DlcErrorCode.REGISTRY_CORRUPT,
        DlcErrorCode.TRUST_STORE_CORRUPT,
        DlcErrorCode.TRUST_STORE_FULL,
        DlcErrorCode.INSTALL_IO_ERROR,
        DlcErrorCode.PACKAGE_MISSING,
    }
)

_PUBLIC_ERROR_DETAILS = {
    DlcErrorCode.TRUST_REQUIRED: "The package is authentic, but its publisher is not trusted.",
    DlcErrorCode.ALREADY_INSTALLED: "This DLC package is already installed.",
    DlcErrorCode.CONFLICTING_DIGEST: "A different package is already installed for this DLC.",
    DlcErrorCode.DLC_NOT_INSTALLED: "The requested DLC is not installed.",
    DlcErrorCode.DLC_VERSION_NOT_INSTALLED: "The requested DLC package version is not installed.",
    DlcErrorCode.DLC_VERSION_SELECTED: "Select a different package version before removing this one.",
    DlcErrorCode.DLC_VERSION_ACTIVE: "Restart DBFox on a different package version before removing this one.",
    DlcErrorCode.DLC_VERSION_LIMIT_REACHED: "Remove an old package version before installing another one.",
    DlcErrorCode.DLC_DISABLE_REQUIRED: "Disable this DLC before uninstalling it.",
    DlcErrorCode.DLC_ACTIVE: "Restart DBFox after disabling this DLC before uninstalling it.",
    DlcErrorCode.PACKAGE_TAMPERED: "The package changed after it was inspected.",
    DlcErrorCode.PUBLISHER_KEY_MISMATCH: "The package publisher does not match the inspected publisher.",
    DlcErrorCode.INVALID_SIGNATURE: "The package signature is invalid.",
    DlcErrorCode.SIGNATURE_REQUIRED: "A valid package signature is required.",
    DlcErrorCode.REGISTRY_CORRUPT: "The installed DLC registry is unavailable or corrupt.",
    DlcErrorCode.TRUST_STORE_CORRUPT: "The trusted publisher store is unavailable or corrupt.",
    DlcErrorCode.TRUST_STORE_FULL: "The trusted publisher store has reached its limit.",
    DlcErrorCode.INSTALL_IO_ERROR: "The DLC package operation could not be completed safely.",
    DlcErrorCode.PACKAGE_MISSING: "The installed DLC package is missing or incomplete.",
}


def _raise_dlc_problem(exc: DlcError) -> NoReturn:
    if exc.code in {
        DlcErrorCode.DLC_NOT_INSTALLED,
        DlcErrorCode.DLC_VERSION_NOT_INSTALLED,
    }:
        http_status = status.HTTP_404_NOT_FOUND
    elif exc.code in _CONFLICT_CODES:
        http_status = status.HTTP_409_CONFLICT
    elif exc.code in _STORAGE_CODES:
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in _BAD_PACKAGE_CODES:
        http_status = status.HTTP_400_BAD_REQUEST
    else:
        http_status = status.HTTP_400_BAD_REQUEST
    raise HTTPException(
        status_code=http_status,
        detail={
            "code": exc.code.value.upper(),
            "message": _PUBLIC_ERROR_DETAILS.get(
                exc.code,
                "The DLC package request was rejected.",
            ),
        },
    ) from exc


def get_dlc_lifecycle_service() -> DlcPackageService:
    try:
        return DlcPackageService(private_runtime_dir("dlcs"))
    except DlcError as exc:
        _raise_dlc_problem(exc)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DLC_STORAGE_UNAVAILABLE",
                "message": "The private DLC storage root is unavailable.",
            },
        ) from exc


def get_dlc_runtime_snapshot() -> RuntimeContributionSnapshot:
    return get_active_runtime_snapshot()


def _inspect_response(service: DlcPackageService, archive_path: str) -> DlcPackageInspection:
    package = service.inspect_from_file(Path(archive_path))
    manifest = package.manifest
    fingerprint = package.publisher_key_id
    if fingerprint is None:
        raise DlcError(
            DlcErrorCode.SIGNATURE_REQUIRED,
            "Product package inspection requires a signed manifest v2 package",
        )
    return DlcPackageInspection(
        dlc_id=manifest.id,
        version=manifest.version,
        display_name=manifest.display_name,
        description=manifest.description,
        publisher=manifest.publisher,
        publisher_fingerprint=fingerprint,
        package_digest=package.package_digest,
        trust_status=package.trust_status,
        trust_required=package.trust_status == DlcTrustStatus.UNTRUSTED,
        permissions=list(manifest.permissions),
        backend_entrypoint_present=(
            manifest.entrypoints.backend is not None
            and manifest.entrypoints.backend in package.integrity.entries
        ),
        frontend_entrypoint_present=(
            manifest.entrypoints.frontend is not None
            and manifest.entrypoints.frontend in package.integrity.entries
        ),
    )


def _lifecycle_item(
    service: DlcPackageService,
    snapshot: RuntimeContributionSnapshot,
    record: InstalledDlcRecord,
) -> DlcLifecycleItem:
    manifest = service.load_installed_manifest(record)
    active_identity = next(
        (item for item in snapshot.active_dlcs if item.dlc_id == record.dlc_id),
        None,
    )
    failure = next(
        (item for item in snapshot.activation_failures if item.dlc_id == record.dlc_id),
        None,
    )
    active_digest = active_identity.package_digest if active_identity is not None else None
    active = active_identity is not None
    exact_active = active_digest == record.selected_digest

    if record.desired_enabled and failure is not None and not exact_active:
        lifecycle_state = DlcLifecycleState.ACTIVATION_FAILED
        restart_state = DlcRestartState.FAILED
    elif record.desired_enabled and exact_active:
        lifecycle_state = DlcLifecycleState.ACTIVE
        restart_state = DlcRestartState.NONE
    elif record.desired_enabled:
        lifecycle_state = DlcLifecycleState.ENABLE_PENDING_RESTART
        restart_state = DlcRestartState.REQUIRED
    elif active:
        lifecycle_state = DlcLifecycleState.DISABLE_PENDING_RESTART
        restart_state = DlcRestartState.REQUIRED
    else:
        lifecycle_state = DlcLifecycleState.INSTALLED_DISABLED
        restart_state = DlcRestartState.NONE

    activation_failure = None
    if failure is not None:
        activation_failure = DlcActivationFailureResponse(
            code=failure.error_code.upper(),
            message=failure.message[:2000],
        )
    return DlcLifecycleItem(
        dlc_id=record.dlc_id,
        version=record.package_version,
        display_name=manifest.display_name,
        description=manifest.description,
        publisher=manifest.publisher,
        publisher_fingerprint=record.publisher_key_id,
        installed_versions=[
            DlcInstalledVersionItem(
                version=item.package_version,
                package_digest=item.package_digest,
                installed_at=item.installed_at,
                selected=item.package_digest == record.selected_digest,
                active=item.package_digest == active_digest,
                pending=(
                    record.desired_enabled
                    and item.package_digest == record.selected_digest
                    and item.package_digest != active_digest
                ),
                removable=(
                    item.package_digest != record.selected_digest
                    and item.package_digest != active_digest
                ),
            )
            for item in record.installed_versions
        ],
        selected_digest=record.selected_digest,
        active_digest=active_digest,
        desired_enabled=record.desired_enabled,
        active=active,
        state=lifecycle_state,
        restart_state=restart_state,
        trust_status=record.trust_status,
        permissions=list(manifest.permissions),
        backend_entrypoint_present=service.entrypoint_is_present(
            record,
            manifest.entrypoints.backend,
        ),
        frontend_entrypoint_present=service.entrypoint_is_present(
            record,
            manifest.entrypoints.frontend,
        ),
        activation_failure=activation_failure,
    )


ServiceDependency = Annotated[DlcPackageService, Depends(get_dlc_lifecycle_service)]
SnapshotDependency = Annotated[
    RuntimeContributionSnapshot,
    Depends(get_dlc_runtime_snapshot),
]


@router.post(
    "/packages/inspect",
    response_model=DlcPackageInspection,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and inspect a local DLC package",
)
async def inspect_dlc_package(
    request: DlcPackageInspectRequest,
    service: ServiceDependency,
) -> DlcPackageInspection:
    try:
        return await run_in_threadpool(_inspect_response, service, request.archive_path)
    except DlcError as exc:
        _raise_dlc_problem(exc)


@router.post(
    "/publishers/trust",
    response_model=DlcPublisherTrustResponse,
    status_code=status.HTTP_200_OK,
    summary="Trust the authenticated publisher of an inspected DLC package",
)
async def trust_dlc_publisher(
    request: DlcPublisherTrustRequest,
    service: ServiceDependency,
) -> DlcPublisherTrustResponse:
    try:
        fingerprint = await run_in_threadpool(
            service.trust_publisher_from_file,
            Path(request.archive_path),
            expected_package_digest=request.package_digest,
            expected_publisher_key_id=request.publisher_fingerprint,
        )
    except DlcError as exc:
        _raise_dlc_problem(exc)
    return DlcPublisherTrustResponse(publisher_fingerprint=fingerprint)


@router.post(
    "/install",
    response_model=DlcLifecycleItem,
    status_code=status.HTTP_201_CREATED,
    summary="Install a trusted DLC package in disabled desired state",
)
async def install_dlc_package(
    request: DlcInstallRequest,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcLifecycleItem:
    try:
        result = await run_in_threadpool(
            service.install_from_file,
            Path(request.archive_path),
        )
        record = service.registry.get_installed_dlc(result.dlc_id)
        if record is None:
            raise DlcError(
                DlcErrorCode.REGISTRY_CORRUPT,
                "Installed record was not readable after commit",
            )
        return await run_in_threadpool(_lifecycle_item, service, snapshot, record)
    except DlcError as exc:
        _raise_dlc_problem(exc)


@router.get(
    "",
    response_model=DlcListResponse,
    status_code=status.HTTP_200_OK,
    summary="List installed DLC desired state and active runtime truth",
)
async def list_dlcs(
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcListResponse:
    try:
        records = await run_in_threadpool(service.registry.list_installed_dlcs)
        items = [
            await run_in_threadpool(_lifecycle_item, service, snapshot, record)
            for record in sorted(records, key=lambda item: item.dlc_id)
        ]
        return DlcListResponse(snapshot_id=snapshot.snapshot_id, dlcs=items)
    except DlcError as exc:
        _raise_dlc_problem(exc)


@router.get(
    "/{dlc_id}",
    response_model=DlcLifecycleItem,
    status_code=status.HTTP_200_OK,
    summary="Get one installed DLC desired state and active runtime truth",
)
async def get_dlc(
    dlc_id: str,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcLifecycleItem:
    try:
        record = await run_in_threadpool(service.registry.get_installed_dlc, dlc_id)
        if record is None:
            raise DlcError(
                DlcErrorCode.DLC_NOT_INSTALLED,
                f"DLC '{dlc_id}' is not installed",
            )
        return await run_in_threadpool(_lifecycle_item, service, snapshot, record)
    except DlcError as exc:
        _raise_dlc_problem(exc)


async def _set_enabled_response(
    dlc_id: str,
    enabled: bool,
    service: DlcPackageService,
    snapshot: RuntimeContributionSnapshot,
) -> DlcLifecycleItem:
    try:
        record = await run_in_threadpool(
            service.set_desired_enabled,
            dlc_id,
            enabled,
        )
        return await run_in_threadpool(_lifecycle_item, service, snapshot, record)
    except DlcError as exc:
        _raise_dlc_problem(exc)


@router.post(
    "/{dlc_id}/enable",
    response_model=DlcLifecycleItem,
    status_code=status.HTTP_200_OK,
    summary="Set desired DLC state to enabled",
)
async def enable_dlc(
    dlc_id: str,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcLifecycleItem:
    return await _set_enabled_response(dlc_id, True, service, snapshot)


@router.post(
    "/{dlc_id}/disable",
    response_model=DlcLifecycleItem,
    status_code=status.HTTP_200_OK,
    summary="Set desired DLC state to disabled",
)
async def disable_dlc(
    dlc_id: str,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcLifecycleItem:
    return await _set_enabled_response(dlc_id, False, service, snapshot)


PackageDigestPath = Annotated[
    str,
    PathParameter(pattern=r"^[0-9a-f]{64}$"),
]


@router.post(
    "/{dlc_id}/versions/{package_digest}/select",
    response_model=DlcLifecycleItem,
    status_code=status.HTTP_200_OK,
    summary="Select one installed DLC package digest for the next restart",
)
async def select_dlc_version(
    dlc_id: str,
    package_digest: PackageDigestPath,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcLifecycleItem:
    try:
        record = await run_in_threadpool(
            service.select_package,
            dlc_id,
            package_digest,
        )
        return await run_in_threadpool(_lifecycle_item, service, snapshot, record)
    except DlcError as exc:
        _raise_dlc_problem(exc)


@router.delete(
    "/{dlc_id}/versions/{package_digest}",
    response_model=DlcVersionRemovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove one inactive, unselected DLC package version",
)
async def remove_dlc_version(
    dlc_id: str,
    package_digest: PackageDigestPath,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcVersionRemovalResponse:
    active_digests = frozenset(item.package_digest for item in snapshot.active_dlcs)
    try:
        result = await run_in_threadpool(
            service.remove_version,
            dlc_id,
            package_digest,
            active_package_digests=active_digests,
        )
    except DlcError as exc:
        _raise_dlc_problem(exc)
    return DlcVersionRemovalResponse(
        dlc_id=result.dlc_id,
        package_digest=result.package_digest,
        executable_bytes_removed=result.executable_bytes_removed,
    )


@router.delete(
    "/{dlc_id}",
    response_model=DlcUninstallResponse,
    status_code=status.HTTP_200_OK,
    summary="Uninstall an inactive, disabled DLC while retaining its data",
)
async def uninstall_dlc(
    dlc_id: str,
    service: ServiceDependency,
    snapshot: SnapshotDependency,
) -> DlcUninstallResponse:
    active_digests = frozenset(item.package_digest for item in snapshot.active_dlcs)
    try:
        result = await run_in_threadpool(
            service.uninstall,
            dlc_id,
            active_package_digests=active_digests,
        )
    except DlcError as exc:
        _raise_dlc_problem(exc)
    return DlcUninstallResponse(
        dlc_id=result.dlc_id,
        package_digest=result.package_digest,
        package_digests=list(result.package_digests),
        executable_bytes_removed=result.executable_bytes_removed,
        data_retained=result.data_retained,
    )
