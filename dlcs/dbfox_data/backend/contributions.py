from __future__ import annotations

from dbfox_dlc_api import (
    BackendExtensionHost,
    DlcOperationContext,
    DlcOperationError,
    DlcOperationSpec,
    SemanticArtifactCompletionSupport,
    SemanticCitationConstraint,
)

from .contracts import (
    AddDatabaseInput,
    BackupCreateInput,
    BackupListInput,
    BackupListOutput,
    BackupRecord,
    BackupRestoreInput,
    CreateProfileInput,
    DatabaseIdInput,
    DatabaseResource,
    DeleteOutput,
    EmptyInput,
    ProfileIdInput,
    ProfileListOutput,
    ProfileWithDatabases,
    RestoreResult,
    UpdateDatabaseInput,
    UpdateProfileInput,
)
from .resource_kind import DATABASE_RESOURCE_KIND
from .artifact_contracts import (
    CHART_ARTIFACT_TYPE,
    RESULT_VIEW_ARTIFACT_TYPE,
    SAFETY_ARTIFACT_TYPE,
    SQL_ARTIFACT_TYPE,
    ChartArtifactPayload,
    ResultViewArtifactPayload,
    SafetyArtifactPayload,
    SqlArtifactPayload,
)
from .store import DataStateStore
from .connection import DataConnectionBoundary
from .backup import DataBackupService
from .catalog_tools import (
    CatalogOverviewTool,
    CatalogRefreshTool,
    SchemaInspectTool,
    SchemaListTool,
    SchemaSearchTool,
)
from .tools import SqlExecuteReadonlyTool, SqlValidateTool
from .preview_tool import DataPreviewTool
from .result_tool import ChartCreateTool, ResultInspectTool, ResultProfileTool
from .result_view import DataChartView, DataResultTableView


def _project_id(context: DlcOperationContext) -> str:
    if not context.project_id:
        raise DlcOperationError(
            code="PROJECT_REQUIRED",
            message="This Data operation requires a Project context",
        )
    return context.project_id


def _safe_error(exc: Exception, *, not_found: bool = False) -> DlcOperationError:
    return DlcOperationError(
        code="DATA_NOT_FOUND" if not_found else "DATA_CONFLICT",
        message=str(exc),
        status_code=404 if not_found else 409,
    )


def _profile_credential_references(input: object) -> frozenset[str]:
    return frozenset(
        str(value)
        for field in (
            "password_credential_ref",
            "ssh_password_credential_ref",
            "ssh_key_passphrase_credential_ref",
        )
        if (value := getattr(input, field, None))
    )


def register(host: BackendExtensionHost) -> None:
    store = DataStateStore(host.runtime_info.data_path)
    backups = DataBackupService(store, host.runtime_info.data_path)
    host.credentials.register_reference_probe(store.owns_credential_references)
    connection = DataConnectionBoundary(
        lambda credential_ref, kind: host.credentials.get(
            credential_ref,
            kind=kind,
        )
    )
    host.tools.register(SqlValidateTool(connection))
    host.tools.register(SqlExecuteReadonlyTool(store, connection))
    host.tools.register(CatalogOverviewTool(store, connection))
    host.tools.register(CatalogRefreshTool(store, connection))
    host.tools.register(SchemaListTool(store, connection))
    host.tools.register(SchemaSearchTool(store, connection))
    host.tools.register(SchemaInspectTool(store, connection))
    host.tools.register(DataPreviewTool(store, connection))
    host.tools.register(ResultInspectTool(store))
    host.tools.register(ResultProfileTool(store))
    host.tools.register(ChartCreateTool(store))

    for artifact_type, validator in (
        (SQL_ARTIFACT_TYPE, SqlArtifactPayload),
        (SAFETY_ARTIFACT_TYPE, SafetyArtifactPayload),
        (RESULT_VIEW_ARTIFACT_TYPE, ResultViewArtifactPayload),
        (CHART_ARTIFACT_TYPE, ChartArtifactPayload),
    ):
        host.artifacts.register(artifact_type, 1, validator)
    table_view = DataResultTableView(store)
    host.artifacts.register_table_view(
        RESULT_VIEW_ARTIFACT_TYPE,
        table_view,
    )
    host.artifacts.register_chart_view(CHART_ARTIFACT_TYPE, DataChartView(table_view))

    host.completion.register_constraint(
        SemanticCitationConstraint(
            id="dbfox.data.result_citation",
            semantic_capability="query_result",
        )
    )
    host.completion.register_support(
        SemanticArtifactCompletionSupport(
            id="dbfox.data.query_result",
            semantic_capability="query_result",
        )
    )

    def list_profiles(_input: EmptyInput, context: DlcOperationContext) -> ProfileListOutput:
        return ProfileListOutput(profiles=store.list_profile_groups(_project_id(context)))

    def create_profile(input: CreateProfileInput, context: DlcOperationContext) -> ProfileWithDatabases:
        try:
            return store.create_profile(project_id=_project_id(context), **input.model_dump())
        except ValueError as exc:
            raise _safe_error(exc) from exc

    def update_profile(input: UpdateProfileInput, context: DlcOperationContext) -> ProfileWithDatabases:
        try:
            return store.update_profile(project_id=_project_id(context), **input.model_dump())
        except ValueError as exc:
            raise _safe_error(exc) from exc

    def delete_profile(input: ProfileIdInput, context: DlcOperationContext) -> DeleteOutput:
        return DeleteOutput(deleted=store.delete_profile(_project_id(context), input.profile_id))

    def add_database(input: AddDatabaseInput, context: DlcOperationContext) -> DatabaseResource:
        try:
            return store.add_database(project_id=_project_id(context), **input.model_dump())
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc
        except ValueError as exc:
            raise _safe_error(exc) from exc

    def delete_database(input: DatabaseIdInput, context: DlcOperationContext) -> DeleteOutput:
        return DeleteOutput(deleted=store.delete_database(_project_id(context), input.database_id))

    def update_database(input: UpdateDatabaseInput, context: DlcOperationContext) -> DatabaseResource:
        try:
            return store.update_database(project_id=_project_id(context), **input.model_dump())
        except ValueError as exc:
            raise _safe_error(exc) from exc

    def list_backups(input: BackupListInput, context: DlcOperationContext) -> BackupListOutput:
        return BackupListOutput(
            backups=backups.list(
                project_id=_project_id(context),
                database_id=input.database_id,
            )
        )

    def create_backup(input: BackupCreateInput, context: DlcOperationContext) -> BackupRecord:
        try:
            return backups.create(
                project_id=_project_id(context),
                database_id=input.database_id,
                label=input.label,
            )
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc
        except ValueError as exc:
            raise _safe_error(exc) from exc
        except Exception as exc:
            raise DlcOperationError(
                code="DATA_BACKUP_FAILED",
                message="The database backup could not be completed.",
                status_code=409,
            ) from exc

    def restore_backup(input: BackupRestoreInput, context: DlcOperationContext) -> RestoreResult:
        try:
            return backups.restore(
                project_id=_project_id(context),
                backup_id=input.backup_id,
                expected_resource_version=input.expected_resource_version,
            )
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc
        except ValueError as exc:
            raise _safe_error(exc) from exc
        except Exception as exc:
            raise DlcOperationError(
                code="DATA_RESTORE_FAILED",
                message="The isolated database restore could not be completed.",
                status_code=409,
            ) from exc

    for spec in (
        DlcOperationSpec(name="profiles.list", input_model=EmptyInput, output_model=ProfileListOutput, handler=list_profiles, scope="project"),
        DlcOperationSpec(
            name="profiles.create",
            input_model=CreateProfileInput,
            output_model=ProfileWithDatabases,
            handler=create_profile,
            scope="project",
            credential_references=_profile_credential_references,
            credential_lease_required=True,
        ),
        DlcOperationSpec(
            name="profiles.update",
            input_model=UpdateProfileInput,
            output_model=ProfileWithDatabases,
            handler=update_profile,
            scope="project",
            credential_references=_profile_credential_references,
        ),
        DlcOperationSpec(name="profiles.delete", input_model=ProfileIdInput, output_model=DeleteOutput, handler=delete_profile, scope="project"),
        DlcOperationSpec(name="databases.add", input_model=AddDatabaseInput, output_model=DatabaseResource, handler=add_database, scope="project"),
        DlcOperationSpec(name="databases.update", input_model=UpdateDatabaseInput, output_model=DatabaseResource, handler=update_database, scope="project"),
        DlcOperationSpec(name="databases.delete", input_model=DatabaseIdInput, output_model=DeleteOutput, handler=delete_database, scope="project"),
        DlcOperationSpec(
            name="backups.list",
            input_model=BackupListInput,
            output_model=BackupListOutput,
            handler=list_backups,
            scope="project",
        ),
        DlcOperationSpec(
            name="backups.create",
            input_model=BackupCreateInput,
            output_model=BackupRecord,
            handler=create_backup,
            scope="project",
            capabilities=("filesystem_read", "filesystem_write"),
        ),
        DlcOperationSpec(
            name="backups.restore",
            input_model=BackupRestoreInput,
            output_model=RestoreResult,
            handler=restore_backup,
            scope="project",
            capabilities=("filesystem_read", "filesystem_write"),
        ),
    ):
        host.operations.register(spec)

    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(DATABASE_RESOURCE_KIND, store.resolve)
