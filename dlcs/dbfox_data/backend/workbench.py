"""Shared Data workbench services used by Tools and typed management operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dbfox_dlc_api import ToolInputError

from .catalog_reflection import DataCatalogReflector
from .connection import DataConnectionBoundary
from .contracts import DatabaseHandle
from .store import DataStateStore
from .tool_contracts import (
    CatalogOverviewOutput,
    CatalogRefreshOutput,
    CatalogTableDetail,
    SchemaInspectInput,
    SchemaInspectOutput,
    SchemaInspection,
    SchemaListCursor,
    SchemaListInput,
    SchemaListOutput,
    TableSummary,
)


class DataCatalogWorkbench:
    """Single catalog implementation for Agent tools and hosted Workbench UI."""

    def __init__(
        self,
        store: DataStateStore,
        connection: DataConnectionBoundary,
    ) -> None:
        self._store = store
        self._reflector = DataCatalogReflector(connection)

    def require_project_database(
        self,
        project_id: str,
        database_id: str,
    ) -> DatabaseHandle:
        return self._store.resolve_project_database(project_id, database_id)

    def overview(self, handle: DatabaseHandle) -> CatalogOverviewOutput:
        state = self._store.catalog_state(handle.database.id)
        initialized = state["refreshed_at"] is not None
        return CatalogOverviewOutput(
            database_id=handle.database.id,
            database_name=handle.database.display_name,
            dialect=handle.profile.provider,
            catalog_status="ready" if initialized else "uninitialized",
            last_sync_at=(
                str(state["refreshed_at"])
                if state["refreshed_at"] is not None
                else None
            ),
            table_count=int(state["table_count"]),
            mode="summary",
            catalog_revision=int(state["catalog_revision"]),
            schemas=list(state["schemas"]),
            domains=[],
            next_action_hint=(
                None
                if initialized
                else "Refresh the catalog once before browsing database objects."
            ),
        )

    def list_tables(
        self,
        handle: DatabaseHandle,
        request: SchemaListInput,
    ) -> SchemaListOutput:
        state = self._store.catalog_state(handle.database.id)
        cursor = request.cursor
        rows, has_more = self._store.list_catalog_tables(
            handle.database.id,
            after=(
                (cursor.schema_name, cursor.table_name, cursor.table_id)
                if cursor is not None
                else None
            ),
            limit=request.limit,
            name_filter=request.name_filter,
        )
        tables = [self._table_summary(row) for row in rows]
        return SchemaListOutput(
            tables=tables,
            next_cursor=(
                SchemaListCursor(
                    schema_name=tables[-1].schema_name,
                    table_name=tables[-1].table_name,
                    table_id=tables[-1].table_id,
                )
                if has_more and tables
                else None
            ),
            returned_count=len(tables),
            has_more=has_more,
            catalog_status=(
                "ready" if state["refreshed_at"] is not None else "uninitialized"
            ),
            catalog_revision=int(state["catalog_revision"]),
        )

    def table(self, handle: DatabaseHandle, name: str) -> CatalogTableDetail:
        table, columns = self._store.resolve_catalog_table(handle.database.id, name)
        state = self._store.catalog_state(handle.database.id)
        return CatalogTableDetail(
            database_id=handle.database.id,
            table={key: value for key, value in table.items() if key != "database_resource_id"},
            columns=[dict(column) for column in columns],
            catalog_revision=int(state["catalog_revision"]),
        )

    def refresh(
        self,
        handle: DatabaseHandle,
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> CatalogRefreshOutput:
        if cancellation_probe and cancellation_probe():
            raise ToolInputError("Catalog refresh was cancelled.")
        inventory = self._reflector.inspect_catalog(
            handle,
            invocation_id=invocation_id,
            cancellation_probe=cancellation_probe,
        )
        result = self._store.replace_catalog(inventory)
        state = self._store.catalog_state(handle.database.id)
        return CatalogRefreshOutput(
            database_id=handle.database.id,
            status="ready",
            refreshed_at=str(state["refreshed_at"]),
            table_count=int(state["table_count"]),
            schema_count=int(state["schema_count"]),
            catalog_revision=int(result.catalog_revision or 0),
            tables_created=result.tables_created,
            tables_updated=result.tables_updated,
            tables_removed=result.tables_removed,
            columns_created=result.columns_created,
            columns_updated=result.columns_updated,
            columns_removed=result.columns_removed,
        )

    def inspect(
        self,
        handle: DatabaseHandle,
        request: SchemaInspectInput,
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> SchemaInspectOutput:
        details = self._reflector.inspect_objects(
            handle,
            request.targets,
            invocation_id=invocation_id,
            cancellation_probe=cancellation_probe,
        )
        state = self._store.catalog_state(handle.database.id)
        return SchemaInspectOutput(
            inspections=[
                SchemaInspection(target=target, details=detail)
                for target, detail in zip(request.targets, details, strict=True)
            ],
            catalog_revision=int(state["catalog_revision"]),
        )

    @staticmethod
    def _table_summary(row: dict[str, Any]) -> TableSummary:
        schema_name = str(row["schema_name"])
        table_name = str(row["table_name"])
        return TableSummary(
            table_id=str(row["id"]),
            schema_name=schema_name,
            table_name=table_name,
            qualified_name=".".join(
                part for part in (schema_name, table_name) if part
            ),
            columns_count=int(row["columns_count"]),
            row_count_estimate=(
                int(row["row_count_estimate"])
                if row["row_count_estimate"] is not None
                else None
            ),
            table_type=str(row["object_type"]),
            comment=str(row["comment"]) if row["comment"] is not None else None,
        )
