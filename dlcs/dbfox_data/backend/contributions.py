from __future__ import annotations

from uuid import uuid4

from dbfox_dlc_api import (
    DATAFRAME_REPRESENTATION_TYPE,
    BackendExtensionHost,
    CapabilityGuidanceSpec,
    DlcOperationContext,
    DlcOperationError,
    DlcOperationSpec,
    RequestedResourceRef,
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
    ConsoleExecuteInput,
    ConsoleExecuteOutput,
    DatabaseIdInput,
    DatabaseResource,
    DeleteOutput,
    EmptyInput,
    ProfileIdInput,
    ProfileListOutput,
    ProfileWithDatabases,
    RestoreResult,
    TablePreviewOperationOutput,
    UpdateDatabaseInput,
    UpdateProfileInput,
)
from .resource_kind import DATABASE_RESOURCE_KIND
from .artifact_contracts import (
    RESULT_VIEW_ARTIFACT_TYPE,
    SNAPSHOT_ARTIFACT_TYPE,
    SAFETY_ARTIFACT_TYPE,
    SQL_ARTIFACT_TYPE,
    ResultViewArtifactPayload,
    SnapshotArtifactPayload,
    SnapshotBackedResultViewArtifactPayload,
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
from .result_tool import ResultInspectTool, ResultProfileTool
from .result_view import DataResultRepresentation
from .tool_contracts import (
    CatalogOverviewOutput,
    CatalogRefreshOutput,
    CatalogTableDetail,
    CatalogTableInput,
    DataPreviewInput,
    SchemaListInput,
    SchemaListOutput,
)
from .workbench import DataCatalogWorkbench


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
    result_representation = DataResultRepresentation(store, connection)
    workbench = DataCatalogWorkbench(store, connection)
    host.tools.register(SqlValidateTool(connection))
    host.tools.register(SqlExecuteReadonlyTool(connection))
    host.tools.register(CatalogOverviewTool(store, connection))
    host.tools.register(CatalogRefreshTool(store, connection))
    host.tools.register(SchemaListTool(store, connection))
    host.tools.register(SchemaSearchTool(store, connection))
    host.tools.register(SchemaInspectTool(store, connection))
    host.tools.register(DataPreviewTool(store, connection))
    host.tools.register(ResultInspectTool(result_representation))
    host.tools.register(ResultProfileTool(result_representation))
    host.agent_guidance.register(CapabilityGuidanceSpec(
        id="analytical_work",
        version="1",
        instructions=(
            "For analytical calculations, establish the relevant grain, time basis, filters, denominator, "
            "and comparison baseline when they can change the answer.\n"
            "Treat samples as samples rather than proof of a population-level claim. For rates, shares, "
            "averages, and growth, make the denominator, missing-value treatment, and baseline explicit.\n"
            "Verify schema semantics before decision-critical computation, and distinguish observed "
            "association from causation."
        ),
        applies_to_resource_kinds=(DATABASE_RESOURCE_KIND,),
        applies_to_artifact_types=(
            SQL_ARTIFACT_TYPE,
            RESULT_VIEW_ARTIFACT_TYPE,
            SNAPSHOT_ARTIFACT_TYPE,
        ),
    ))

    for artifact_type, validator in (
        (SQL_ARTIFACT_TYPE, SqlArtifactPayload),
        (SAFETY_ARTIFACT_TYPE, SafetyArtifactPayload),
        (RESULT_VIEW_ARTIFACT_TYPE, SnapshotBackedResultViewArtifactPayload),
        (SNAPSHOT_ARTIFACT_TYPE, SnapshotArtifactPayload),
    ):
        host.artifacts.register(artifact_type, 1, validator)
    host.artifacts.register(RESULT_VIEW_ARTIFACT_TYPE, 2, ResultViewArtifactPayload)
    host.artifacts.register_representation(
        RESULT_VIEW_ARTIFACT_TYPE,
        DATAFRAME_REPRESENTATION_TYPE,
        result_representation,
    )
    host.artifacts.register_representation(
        SNAPSHOT_ARTIFACT_TYPE,
        DATAFRAME_REPRESENTATION_TYPE,
        result_representation,
    )

    host.completion.register_constraint(
        SemanticCitationConstraint(
            id="dbfox.data.result_citation",
            semantic_capability="dbfox.data.query_result",
        )
    )
    host.completion.register_support(
        SemanticArtifactCompletionSupport(
            id="dbfox.data.query_result",
            semantic_capability="dbfox.data.query_result",
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

    def catalog_overview(
        input: DatabaseIdInput,
        context: DlcOperationContext,
    ) -> CatalogOverviewOutput:
        try:
            handle = workbench.require_project_database(
                _project_id(context), input.database_id
            )
            return workbench.overview(handle)
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc

    def catalog_tables(
        input: SchemaListInput,
        context: DlcOperationContext,
    ) -> SchemaListOutput:
        if not input.database_id:
            raise DlcOperationError(
                code="DATA_DATABASE_REQUIRED",
                message="Database resource is required",
                status_code=400,
            )
        try:
            handle = workbench.require_project_database(
                _project_id(context), input.database_id
            )
            return workbench.list_tables(handle, input)
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc

    def catalog_table(
        input: CatalogTableInput,
        context: DlcOperationContext,
    ) -> CatalogTableDetail:
        if not input.database_id:
            raise DlcOperationError(
                code="DATA_DATABASE_REQUIRED",
                message="Database resource is required",
                status_code=400,
            )
        try:
            handle = workbench.require_project_database(
                _project_id(context), input.database_id
            )
            return workbench.table(handle, input.table)
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc
        except ValueError as exc:
            raise _safe_error(exc) from exc

    def catalog_refresh(
        input: DatabaseIdInput,
        context: DlcOperationContext,
    ) -> CatalogRefreshOutput:
        try:
            handle = workbench.require_project_database(
                _project_id(context), input.database_id
            )
            return workbench.refresh(
                handle,
                invocation_id=f"workbench_catalog_{uuid4().hex}",
            )
        except KeyError as exc:
            raise _safe_error(exc, not_found=True) from exc
        except Exception as exc:
            raise DlcOperationError(
                code="DATA_CATALOG_REFRESH_FAILED",
                message="The database catalog could not be refreshed.",
                status_code=409,
            ) from exc

    def console_execute(
        input: ConsoleExecuteInput,
        context: DlcOperationContext,
    ) -> ConsoleExecuteOutput:
        action_runs = context.require_action_runs()
        requested = (
            RequestedResourceRef(
                kind=DATABASE_RESOURCE_KIND,
                id=input.database_id,
            ),
        )
        with action_runs.start(
            title="SQL Console",
            question=input.question or "SQL Console",
            requested_resources=requested,
            session_id=input.session_id,
            idempotency_key=(
                f"data-console:{input.execution_id}"
                if input.execution_id
                else None
            ),
        ) as action:
            validation = action.invoke(
                "sql_validate",
                {"database_id": input.database_id, "sql": input.sql},
            )
            if validation.status != "success":
                raise DlcOperationError(
                    code="DATA_SQL_VALIDATION_FAILED",
                    message="The SQL could not be validated.",
                    status_code=409,
                )
            sql_artifact = next(
                (item for item in validation.artifacts if item.type == SQL_ARTIFACT_TYPE),
                None,
            )
            safety_artifact = next(
                (item for item in validation.artifacts if item.type == SAFETY_ARTIFACT_TYPE),
                None,
            )
            if sql_artifact is None or safety_artifact is None:
                raise DlcOperationError(
                    code="DATA_SQL_ARTIFACT_MISSING",
                    message="SQL validation did not produce its durable Artifact chain.",
                    status_code=409,
                )
            messages = [str(value) for value in validation.output.get("messages") or []]
            if not bool(validation.output.get("can_execute")):
                completed = action.complete(summary="SQL validation blocked execution.")
                return ConsoleExecuteOutput(
                    status="blocked",
                    run_id=completed.run_id,
                    session_id=completed.session_id,
                    sql_artifact_id=sql_artifact.id,
                    safety_artifact_id=safety_artifact.id,
                    messages=messages,
                )

            execution = action.invoke(
                "sql_execute_readonly",
                {
                    "database_id": input.database_id,
                    "validation_artifact_id": sql_artifact.id,
                },
            )
            if execution.status != "success":
                raise DlcOperationError(
                    code="DATA_SQL_EXECUTION_FAILED",
                    message="The validated read-only query could not be executed.",
                    status_code=409,
                )
            result_artifact = next(
                (
                    item
                    for item in execution.artifacts
                    if item.type == RESULT_VIEW_ARTIFACT_TYPE
                ),
                None,
            )
            if result_artifact is None:
                raise DlcOperationError(
                    code="DATA_RESULT_ARTIFACT_MISSING",
                    message="Query execution did not produce a durable Result Artifact.",
                    status_code=409,
                )
            completed = action.complete(
                summary="SQL Console execution completed.",
                selected_artifact_id=result_artifact.id,
            )
            return ConsoleExecuteOutput(
                status="success",
                run_id=completed.run_id,
                session_id=completed.session_id,
                sql_artifact_id=sql_artifact.id,
                safety_artifact_id=safety_artifact.id,
                result_artifact_id=result_artifact.id,
                columns=[str(value) for value in execution.output.get("columns") or []],
                rows=list(execution.output.get("rows") or []),
                row_count=int(execution.output.get("row_count") or 0),
                returned_rows=int(execution.output.get("returned_rows") or 0),
                truncated=bool(execution.output.get("truncated")),
                warnings=[str(value) for value in execution.output.get("warnings") or []],
                messages=messages,
            )

    def table_preview(
        input: DataPreviewInput,
        context: DlcOperationContext,
    ) -> TablePreviewOperationOutput:
        if not input.database_id:
            raise DlcOperationError(
                code="DATA_DATABASE_REQUIRED",
                message="Database resource is required",
                status_code=400,
            )
        with context.require_action_runs().start(
            title="Table Preview",
            question=f"Preview {input.table}",
            requested_resources=(
                RequestedResourceRef(
                    kind=DATABASE_RESOURCE_KIND,
                    id=input.database_id,
                ),
            ),
        ) as action:
            preview = action.invoke("data_preview", input.model_dump(mode="json"))
            if preview.status != "success":
                raise DlcOperationError(
                    code="DATA_PREVIEW_FAILED",
                    message="The table preview could not be loaded.",
                    status_code=409,
                )
            result_artifact = next(
                (
                    item
                    for item in preview.artifacts
                    if item.type == RESULT_VIEW_ARTIFACT_TYPE
                ),
                None,
            )
            if result_artifact is None:
                raise DlcOperationError(
                    code="DATA_RESULT_ARTIFACT_MISSING",
                    message="Table preview did not produce a durable Result Artifact.",
                    status_code=409,
                )
            completed = action.complete(
                summary="Table preview completed.",
                selected_artifact_id=result_artifact.id,
            )
            return TablePreviewOperationOutput(
                run_id=completed.run_id,
                session_id=completed.session_id,
                result_artifact_id=result_artifact.id,
                table=str(preview.output.get("table") or input.table),
                columns=[str(value) for value in preview.output.get("columns") or []],
                rows=list(preview.output.get("rows") or []),
                returned_rows=int(preview.output.get("returned_rows") or 0),
                truncated=bool(preview.output.get("truncated")),
                warnings=[str(value) for value in preview.output.get("warnings") or []],
            )

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
        DlcOperationSpec(name="catalog.overview", input_model=DatabaseIdInput, output_model=CatalogOverviewOutput, handler=catalog_overview, scope="project"),
        DlcOperationSpec(name="catalog.tables", input_model=SchemaListInput, output_model=SchemaListOutput, handler=catalog_tables, scope="project"),
        DlcOperationSpec(name="catalog.table", input_model=CatalogTableInput, output_model=CatalogTableDetail, handler=catalog_table, scope="project"),
        DlcOperationSpec(
            name="console.execute",
            input_model=ConsoleExecuteInput,
            output_model=ConsoleExecuteOutput,
            handler=console_execute,
            scope="project",
            capabilities=("network", "filesystem_read"),
        ),
        DlcOperationSpec(
            name="table.preview",
            input_model=DataPreviewInput,
            output_model=TablePreviewOperationOutput,
            handler=table_preview,
            scope="project",
            capabilities=("network", "filesystem_read"),
        ),
        DlcOperationSpec(
            name="catalog.refresh",
            input_model=DatabaseIdInput,
            output_model=CatalogRefreshOutput,
            handler=catalog_refresh,
            scope="project",
            capabilities=("network", "filesystem_read"),
        ),
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
