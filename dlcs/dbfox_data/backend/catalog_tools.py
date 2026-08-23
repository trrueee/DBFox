"""Catalog tools contributed by the dbfox.data System DLC."""

from __future__ import annotations

import re
from typing import Any

from dbfox_dlc_api import (
    BaseTool,
    ExtensionToolRunContext,
    ToolExecutionSpec,
    ToolInputError,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .connection import DataConnectionBoundary
from .database_selection import select_database
from .resource_kind import DATABASE_RESOURCE_KIND
from .store import DataStateStore
from .workbench import DataCatalogWorkbench
from .tool_contracts import (
    CatalogOverviewOutput,
    CatalogRefreshOutput,
    DatabaseTargetInput,
    SchemaInspectInput,
    SchemaInspectOutput,
    SchemaListInput,
    SchemaListOutput,
    SchemaSearchInput,
    SchemaSearchOutput,
    SearchResultSet,
)


def _tokens(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query.casefold()):
        if token not in tokens:
            tokens.append(token)
        if len(tokens) == 32:
            break
    return tuple(tokens)


class _CatalogTool:
    def __init__(
        self,
        store: DataStateStore,
        connection: DataConnectionBoundary,
    ) -> None:
        self._store = store
        self._connection = connection
        self._workbench = DataCatalogWorkbench(store, connection)

    def cancel(self, invocation_id: str) -> None:
        self._connection.cancel(invocation_id)


class CatalogOverviewTool(
    _CatalogTool,
    BaseTool[DatabaseTargetInput, CatalogOverviewOutput],
):
    name = "catalog_overview"
    group = "catalog"
    description = (
        "Return a bounded overview of the selected database catalog, including "
        "refresh state, revision, table count, and schema summaries."
    )
    input_model = DatabaseTargetInput
    output_model = CatalogOverviewOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=("environment_profile", "schema_metadata")
    )
    presentation = ToolPresentation(title="了解数据库目录", category="explore")

    def run(
        self,
        tool_input: DatabaseTargetInput,
        context: ExtensionToolRunContext,
    ) -> CatalogOverviewOutput:
        _ref, handle = select_database(context, tool_input.database_id)
        return self._workbench.overview(handle)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库目录概览获取失败。")
        return ToolObservationProjection(
            summary=f"数据库目录概览已获取，共 {int(output.get('table_count') or 0)} 张表。",
            facts={
                "database_id": output.get("database_id"),
                "dialect": output.get("dialect"),
                "catalog_status": output.get("catalog_status"),
                "table_count": output.get("table_count"),
                "catalog_revision": output.get("catalog_revision"),
                "schemas": list(output.get("schemas") or [])[:30],
            },
        )


class CatalogRefreshTool(
    _CatalogTool,
    BaseTool[DatabaseTargetInput, CatalogRefreshOutput],
):
    name = "catalog_refresh"
    group = "catalog"
    description = (
        "Read the selected database metadata and atomically replace DBFox's local "
        "catalog. This never modifies the remote database."
    )
    input_model = DatabaseTargetInput
    output_model = CatalogRefreshOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        timeout_seconds=120,
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(
        produces=("environment_profile", "schema_metadata")
    )
    presentation = ToolPresentation(
        title="刷新数据库目录",
        category="explore",
        progress="indeterminate",
    )

    def run(
        self,
        tool_input: DatabaseTargetInput,
        context: ExtensionToolRunContext,
    ) -> CatalogRefreshOutput:
        _ref, handle = select_database(context, tool_input.database_id)
        if context.is_cancelled():
            raise ToolInputError("Catalog refresh was cancelled.")
        try:
            return self._workbench.refresh(
                handle,
                invocation_id=context.invocation_id,
                cancellation_probe=context.is_cancelled,
            )
        except ToolInputError:
            raise
        except Exception as exc:
            raise ToolInputError("Database catalog refresh failed.") from exc

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库目录刷新失败。")
        return ToolObservationProjection(
            summary=f"数据库目录已刷新，共 {int(output.get('table_count') or 0)} 张表。",
            facts={
                "database_id": output.get("database_id"),
                "status": output.get("status"),
                "refreshed_at": output.get("refreshed_at"),
                "table_count": output.get("table_count"),
                "schema_count": output.get("schema_count"),
                "catalog_revision": output.get("catalog_revision"),
            },
        )


class SchemaListTool(
    _CatalogTool,
    BaseTool[SchemaListInput, SchemaListOutput],
):
    name = "schema_list"
    group = "catalog"
    description = (
        "Browse bounded table summaries from the local catalog with a stable cursor."
    )
    input_model = SchemaListInput
    output_model = SchemaListOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(produces=("schema_metadata",))
    presentation = ToolPresentation(title="浏览数据表", category="explore")

    def run(
        self,
        tool_input: SchemaListInput,
        context: ExtensionToolRunContext,
    ) -> SchemaListOutput:
        _ref, handle = select_database(context, tool_input.database_id)
        return self._workbench.list_tables(handle, tool_input)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据表目录浏览失败。")
        return ToolObservationProjection(
            summary=f"已浏览 {int(output.get('returned_count') or 0)} 张表。",
            facts={
                "tables": list(output.get("tables") or []),
                "returned_count": output.get("returned_count"),
                "next_cursor": output.get("next_cursor"),
                "has_more": output.get("has_more"),
                "catalog_revision": output.get("catalog_revision"),
            },
        )


class SchemaSearchTool(
    _CatalogTool,
    BaseTool[SchemaSearchInput, SchemaSearchOutput],
):
    name = "schema_search"
    group = "catalog"
    description = (
        "Search table and column names and comments in the selected database catalog."
    )
    input_model = SchemaSearchInput
    output_model = SchemaSearchOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(produces=("schema_metadata",))
    presentation = ToolPresentation(title="查找相关表和字段", category="explore")

    def run(
        self,
        tool_input: SchemaSearchInput,
        context: ExtensionToolRunContext,
    ) -> SchemaSearchOutput:
        _ref, handle = select_database(context, tool_input.database_id)
        searches: list[SearchResultSet] = []
        candidates: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for query in tool_input.queries:
            tokens = _tokens(query)
            results = self._store.search_catalog(
                handle.database.id,
                tokens,
                tool_input.limit_per_query,
            )
            searches.append(
                SearchResultSet(
                    query=query,
                    engine="sqlite_catalog",
                    tokens=list(tokens),
                    results=results,
                    returned_count=len(results),
                )
            )
            for item in results:
                key = (
                    str(item.get("type") or ""),
                    str(item.get("schema_name") or ""),
                    str(item.get("table_name") or ""),
                    str(item.get("column_name") or ""),
                )
                candidate = candidates.get(key)
                if candidate is None:
                    candidate = dict(item)
                    candidate["matched_queries"] = [query]
                    candidates[key] = candidate
                else:
                    candidate["matched_queries"].append(query)
                    candidate["score"] = max(
                        float(candidate.get("score") or 0),
                        float(item.get("score") or 0),
                    )
        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                -float(item.get("score") or 0),
                str(item.get("schema_name") or ""),
                str(item.get("name") or ""),
            ),
        )
        state = self._store.catalog_state(handle.database.id)
        return SchemaSearchOutput(
            searches=searches,
            candidates=ranked,
            returned_count=len(ranked),
            catalog_revision=int(state["catalog_revision"]),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库对象搜索失败。")
        candidates = list(output.get("candidates") or [])
        return ToolObservationProjection(
            summary=f"数据库对象搜索完成，得到 {len(candidates)} 个候选项。",
            facts={
                "returned_count": len(candidates),
                "candidates": candidates[:20],
                "catalog_revision": output.get("catalog_revision"),
            },
        )


class SchemaInspectTool(
    _CatalogTool,
    BaseTool[SchemaInspectInput, SchemaInspectOutput],
):
    name = "schema_inspect"
    group = "catalog"
    description = (
        "Live-inspect one to five authorized database tables or columns, including "
        "keys, indexes, and relationships."
    )
    input_model = SchemaInspectInput
    output_model = SchemaInspectOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(produces=("schema_metadata",))
    presentation = ToolPresentation(title="检查数据库对象", category="explore")

    def run(
        self,
        tool_input: SchemaInspectInput,
        context: ExtensionToolRunContext,
    ) -> SchemaInspectOutput:
        _ref, handle = select_database(context, tool_input.database_id)
        try:
            return self._workbench.inspect(
                handle,
                tool_input,
                invocation_id=context.invocation_id,
                cancellation_probe=context.is_cancelled,
            )
        except ToolInputError:
            raise
        except Exception as exc:
            raise ToolInputError("Database object inspection failed.") from exc

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库对象结构检查失败。")
        inspections = list(output.get("inspections") or [])
        return ToolObservationProjection(
            summary=f"已检查 {len(inspections)} 个数据库对象。",
            facts={
                "inspections": inspections,
                "inspection_count": len(inspections),
                "catalog_revision": output.get("catalog_revision"),
            },
        )
