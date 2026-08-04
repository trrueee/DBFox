from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_

from engine.environment.schema_catalog_sync import SchemaCatalogSync
from engine.errors import ToolInputError
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.tools.builtin.contracts import (
    CatalogOverviewOutput,
    CatalogRefreshOutput,
    EmptyInput,
    SchemaInspectInput,
    SchemaInspectOutput,
    SchemaInspection,
    SchemaListInput,
    SchemaListCursor,
    SchemaListOutput,
    SchemaSearchInput,
    SchemaSearchOutput,
    SearchResultSet,
    TableSummary,
)
from engine.tools.db.inspect import db_inspect
from engine.tools.db.observe import db_observe
from engine.tools.db.search import db_search
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
    ToolRunContext,
    ToolSemanticCapability,
    ToolSemanticSpec,
)
from engine.tools.runtime.observation import safe_observation_facts


class CatalogOverviewTool(BaseTool[EmptyInput, CatalogOverviewOutput]):
    name = "catalog_overview"
    group = "catalog"
    description = (
        "Return a bounded overview of the current datasource: dialect, catalog "
        "freshness, table count, schema/domain summaries, and warnings. Use once "
        "when orientation is needed. If it reports an empty or stale catalog, call "
        "catalog_refresh once before searching; otherwise do not repeat this call."
    )
    input_model = EmptyInput
    output_model = CatalogOverviewOutput
    presentation = ToolPresentation(title="了解数据库目录", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=(
            ToolSemanticCapability.ENVIRONMENT_PROFILE,
            ToolSemanticCapability.SCHEMA_METADATA,
        )
    )

    def run(
        self,
        tool_input: EmptyInput,
        context: ToolRunContext,
    ) -> CatalogOverviewOutput:
        db = context.require_database()
        request = context.require_request()
        return CatalogOverviewOutput.model_validate(
            db_observe(db, request.datasource_id)
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库目录概览获取失败。")
        return ToolObservationProjection(
            summary=(
                f"数据库目录概览已获取，共 {int(output.get('table_count') or 0)} 张表。"
            ),
            facts=safe_observation_facts(
                {
                    "dialect": output.get("dialect"),
                    "catalog_status": output.get("catalog_status"),
                    "table_count": output.get("table_count"),
                    "mode": output.get("mode"),
                    "warnings": output.get("warnings") or [],
                }
            ),
        )


class CatalogRefreshTool(BaseTool[EmptyInput, CatalogRefreshOutput]):
    name = "catalog_refresh"
    group = "catalog"
    description = (
        "Refresh DBFox's local metadata catalog from the current datasource. Use "
        "only when catalog_overview reports empty or stale metadata, or when the "
        "user explicitly asks to refresh schema metadata. This reads the remote "
        "catalog and replaces local metadata atomically; it never changes the "
        "remote datasource."
    )
    input_model = EmptyInput
    output_model = CatalogRefreshOutput
    presentation = ToolPresentation(
        title="刷新数据库目录",
        category="explore",
        progress="indeterminate",
    )
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        timeout_seconds=120,
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "metadata_write", "database_read"),
    )
    semantics = ToolSemanticSpec(
        produces=(
            ToolSemanticCapability.ENVIRONMENT_PROFILE,
            ToolSemanticCapability.SCHEMA_METADATA,
        )
    )

    def run(
        self,
        tool_input: EmptyInput,
        context: ToolRunContext,
    ) -> CatalogRefreshOutput:
        if context.is_cancelled():
            raise ToolInputError("Catalog refresh was cancelled.")

        db = context.require_database()
        request = context.require_request()
        datasource_id = request.datasource_id
        result = SchemaCatalogSync().sync(
            db,
            datasource_id,
            ai_enrich=False,
        )
        datasource = db.get(DataSource, datasource_id)
        if datasource is None or datasource.last_sync_at is None:
            raise ToolInputError("The datasource is unavailable after catalog refresh.")

        table_count = (
            db.query(func.count(SchemaTable.id))
            .filter(SchemaTable.data_source_id == datasource_id)
            .scalar()
            or 0
        )
        schema_count = (
            db.query(
                func.count(func.distinct(SchemaTable.table_schema))
            )
            .filter(SchemaTable.data_source_id == datasource_id)
            .scalar()
            or 0
        )
        return CatalogRefreshOutput(
            datasource_id=datasource_id,
            status="ready",
            refreshed_at=datasource.last_sync_at.isoformat(),
            table_count=int(table_count),
            schema_count=int(schema_count),
            tables_created=result.tables_created,
            tables_updated=result.tables_updated,
            tables_removed=result.tables_removed,
            columns_created=result.columns_created,
            columns_updated=result.columns_updated,
            columns_removed=result.columns_removed,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库目录刷新失败。")
        return ToolObservationProjection(
            summary=(
                f"数据库目录已刷新，共 {int(output.get('table_count') or 0)} 张表。"
            ),
            facts=safe_observation_facts(
                {
                    "status": output.get("status"),
                    "refreshed_at": output.get("refreshed_at"),
                    "table_count": output.get("table_count"),
                    "schema_count": output.get("schema_count"),
                    "tables_created": output.get("tables_created"),
                    "tables_updated": output.get("tables_updated"),
                    "tables_removed": output.get("tables_removed"),
                }
            ),
        )


class SchemaListTool(BaseTool[SchemaListInput, SchemaListOutput]):
    name = "schema_list"
    group = "catalog"
    description = (
        "Browse table-level catalog summaries with stable cursor pagination. "
        "Use only when semantic search is insufficient or the user asks to browse "
        "the catalog; never dump the entire catalog."
    )
    input_model = SchemaListInput
    output_model = SchemaListOutput
    presentation = ToolPresentation(title="浏览数据表", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.SCHEMA_METADATA,)
    )

    def run(
        self,
        tool_input: SchemaListInput,
        context: ToolRunContext,
    ) -> SchemaListOutput:
        db = context.require_database()
        request = context.require_request()
        filters: list[Any] = [
            SchemaTable.data_source_id == request.datasource_id
        ]
        if tool_input.cursor:
            cursor = tool_input.cursor
            filters.append(
                or_(
                    SchemaTable.table_schema > cursor.schema_name,
                    and_(
                        SchemaTable.table_schema == cursor.schema_name,
                        SchemaTable.table_name > cursor.table_name,
                    ),
                    and_(
                        SchemaTable.table_schema == cursor.schema_name,
                        SchemaTable.table_name == cursor.table_name,
                        SchemaTable.id > cursor.table_id,
                    ),
                )
            )
        if tool_input.name_filter:
            filters.append(
                SchemaTable.table_name.ilike(f"%{tool_input.name_filter}%")
            )
        rows = (
            db.query(
                SchemaTable.id,
                SchemaTable.table_schema,
                SchemaTable.table_name,
                SchemaTable.row_count_estimate,
                SchemaTable.table_type,
                SchemaTable.table_comment,
                func.count(SchemaColumn.id).label("columns_count"),
            )
            .outerjoin(SchemaColumn, SchemaColumn.table_id == SchemaTable.id)
            .filter(*filters)
            .group_by(
                SchemaTable.id,
                SchemaTable.table_schema,
                SchemaTable.table_name,
                SchemaTable.row_count_estimate,
                SchemaTable.table_type,
                SchemaTable.table_comment,
            )
            .order_by(
                SchemaTable.table_schema,
                SchemaTable.table_name,
                SchemaTable.id,
            )
            .limit(tool_input.limit + 1)
            .all()
        )
        has_more = len(rows) > tool_input.limit
        page = rows[: tool_input.limit]
        tables = [
            TableSummary(
                table_id=str(row.id),
                schema_name=str(row.table_schema or ""),
                table_name=str(row.table_name),
                qualified_name=(
                    f"{row.table_schema}.{row.table_name}"
                    if row.table_schema
                    else str(row.table_name)
                ),
                columns_count=int(row.columns_count or 0),
                row_count_estimate=(
                    int(row.row_count_estimate)
                    if row.row_count_estimate is not None
                    else None
                ),
                table_type=str(row.table_type or "table"),
                comment=(
                    str(row.table_comment)
                    if row.table_comment is not None
                    else None
                ),
            )
            for row in page
        ]
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
            catalog_status="empty" if not tables and not tool_input.cursor else "ready",
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据表目录浏览失败。")
        return ToolObservationProjection(
            summary=f"已浏览 {int(output.get('returned_count') or 0)} 张表。",
            facts=safe_observation_facts(
                {
                    # The list is already bounded by SchemaListInput.limit and
                    # safe_observation_facts enforces the model-context byte
                    # ceiling.  Omitting it leaves the model with a count but
                    # no catalog evidence to reason from.
                    "tables": output.get("tables") or [],
                    "returned_count": output.get("returned_count"),
                    "next_cursor": output.get("next_cursor"),
                    "has_more": output.get("has_more"),
                }
            ),
        )


class SchemaSearchTool(BaseTool[SchemaSearchInput, SchemaSearchOutput]):
    name = "schema_search"
    group = "catalog"
    description = (
        "Search table names, column names, comments, aliases, and enriched business "
        "metadata. Submit one to four complementary expressions in one call; the "
        "tool returns per-query evidence and one deduplicated candidate list."
    )
    input_model = SchemaSearchInput
    output_model = SchemaSearchOutput
    presentation = ToolPresentation(title="查找相关表和字段", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.SCHEMA_METADATA,)
    )

    def run(
        self,
        tool_input: SchemaSearchInput,
        context: ToolRunContext,
    ) -> SchemaSearchOutput:
        db = context.require_database()
        request = context.require_request()
        searches: list[SearchResultSet] = []
        candidates: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for query in tool_input.queries:
            raw = db_search(
                db,
                request.datasource_id,
                query,
                tool_input.limit_per_query,
            )
            results = list(raw.get("results") or [])
            searches.append(
                SearchResultSet(
                    query=query,
                    engine=str(raw.get("engine") or "unknown"),
                    tokens=[str(token) for token in raw.get("tokens") or []],
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
                    matched = list(candidate.get("matched_queries") or [])
                    if query not in matched:
                        matched.append(query)
                    candidate["matched_queries"] = matched
                    candidate["score"] = max(
                        float(candidate.get("score") or 0),
                        float(item.get("score") or 0),
                    )
        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                -float(item.get("score") or 0),
                str(item.get("schema_name") or ""),
                str(item.get("table_name") or ""),
                str(item.get("column_name") or ""),
            ),
        )
        return SchemaSearchOutput(
            searches=searches,
            candidates=ranked,
            returned_count=len(ranked),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库对象搜索失败。")
        candidates = list(output.get("candidates") or [])
        return ToolObservationProjection(
            summary=f"数据库对象搜索完成，得到 {len(candidates)} 个候选项。",
            facts=safe_observation_facts(
                {
                    "returned_count": len(candidates),
                    "candidates": candidates[:20],
                }
            ),
        )


class SchemaInspectTool(BaseTool[SchemaInspectInput, SchemaInspectOutput]):
    name = "schema_inspect"
    group = "catalog"
    description = (
        "Live-inspect one to five candidate tables or columns. Returns columns, keys, "
        "indexes, row estimates, and incoming/outgoing relationships so the source "
        "can be verified before writing SQL."
    )
    input_model = SchemaInspectInput
    output_model = SchemaInspectOutput
    presentation = ToolPresentation(title="检查数据库对象", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.SCHEMA_METADATA,)
    )

    def run(
        self,
        tool_input: SchemaInspectInput,
        context: ToolRunContext,
    ) -> SchemaInspectOutput:
        db = context.require_database()
        request = context.require_request()
        details = db_inspect(
            db,
            request.datasource_id,
            tool_input.targets,
        )
        return SchemaInspectOutput(
            inspections=[
                SchemaInspection(
                    target=target,
                    details=detail,
                )
                for target, detail in zip(
                    tool_input.targets,
                    details,
                    strict=True,
                )
            ]
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据库对象结构检查失败。")
        inspections = list(output.get("inspections") or [])
        return ToolObservationProjection(
            summary=f"已检查 {len(inspections)} 个数据库对象。",
            facts=safe_observation_facts({"inspections": inspections}),
        )
