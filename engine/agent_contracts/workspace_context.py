from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy.orm import Session, selectinload

from engine.agent_contracts.context import schema_linking_question
from engine.agent_contracts.types import AgentContextArtifact, AgentRunRequest, AgentWorkspaceContext
from engine.models import (
    AgentArtifactRecord,
    AgentRun,
    DataSource,
    SchemaTable,
    SemanticAlias,
    SemanticDimension,
    SemanticMetric,
    WorkspaceTableScope,
)
from engine.semantic import SchemaContextBuilder, SchemaLinker


MAX_SQL_CHARS = 6000
MAX_CONTEXT_CHARS = 4800
MAX_RESULT_ROWS = 20
MAX_TABLES = 8
MAX_COLUMNS_PER_TABLE = 24


def build_agent_context_bundle(db: Session, req: AgentRunRequest) -> dict[str, Any]:
    workspace = req.workspace_context or AgentWorkspaceContext(datasource_id=req.datasource_id)
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    selected_tables = _selected_tables(db, req.datasource_id, workspace)
    linking_payload = _schema_linking_payload(db, req, workspace, selected_tables)
    selected_artifact = _selected_artifact_payload(db, req, workspace)
    recent_run = _recent_run_summary(db, req, workspace)
    semantic_context = _semantic_context(db, req.datasource_id, workspace)

    bundle = {
        "datasource": _datasource_payload(datasource, req.datasource_id),
        "workspace": {
            "project_id": workspace.project_id,
            "datasource_id": req.datasource_id,
            "active_sql": _compact_text(workspace.active_sql, MAX_SQL_CHARS),
            "selected_sql": _compact_text(workspace.selected_sql, MAX_SQL_CHARS),
            "last_query_result_preview": _preview_result(workspace.last_query_result_preview),
            "last_error": _compact_text(workspace.last_error, 1200),
            "selected_table_ids": [str(item) for item in workspace.selected_table_ids[:MAX_TABLES]],
            "selected_table_names": [str(item) for item in workspace.selected_table_names[:MAX_TABLES]],
            "selected_column_refs": [str(item) for item in workspace.selected_column_refs[:64]],
            "selected_artifact_id": workspace.selected_artifact_id,
            "recent_agent_run_id": workspace.recent_agent_run_id,
            "open_sql_tabs": _preview_sql_tabs(workspace.open_sql_tabs),
            "editor_annotations": _safe_json_list(workspace.editor_annotations, limit=32),
        },
        "selected_table_schema": [_table_payload(table) for table in selected_tables],
        "selected_artifact": selected_artifact,
        "recent_agent_run": recent_run,
        "semantic_context": semantic_context,
        "schema_linking": linking_payload,
    }
    bundle["context_summary"] = _context_summary(bundle)
    return bundle


def _datasource_payload(datasource: DataSource | None, datasource_id: str) -> dict[str, Any]:
    if datasource is None:
        return {"id": datasource_id, "found": False}
    return {
        "id": datasource.id,
        "project_id": datasource.project_id,
        "name": datasource.name,
        "db_type": datasource.db_type,
        "database_name": datasource.database_name,
        "env": datasource.env,
        "status": datasource.status,
        "is_read_only": bool(datasource.is_read_only),
        "last_sync_status": datasource.last_sync_status,
        "last_sync_at": datasource.last_sync_at.isoformat() if datasource.last_sync_at else None,
    }


def _selected_tables(
    db: Session,
    datasource_id: str,
    workspace: AgentWorkspaceContext,
) -> list[SchemaTable]:
    query = (
        db.query(SchemaTable)
        .options(selectinload(SchemaTable.columns))
        .filter(SchemaTable.data_source_id == datasource_id)
    )
    filters = []
    if workspace.selected_table_ids:
        filters.append(SchemaTable.id.in_([str(item) for item in workspace.selected_table_ids]))
    if workspace.selected_table_names:
        filters.append(SchemaTable.table_name.in_([str(item) for item in workspace.selected_table_names]))
    if not filters:
        return []
    if len(filters) == 1:
        query = query.filter(filters[0])
    else:
        from sqlalchemy import or_

        query = query.filter(or_(*filters))
    return query.order_by(SchemaTable.table_name.asc()).limit(MAX_TABLES).all()


def _schema_linking_payload(
    db: Session,
    req: AgentRunRequest,
    workspace: AgentWorkspaceContext,
    selected_tables: list[SchemaTable],
) -> dict[str, Any]:
    question = _linking_question(req, workspace)
    linker = SchemaLinker(db)
    workspace_ids = [str(table.id) for table in selected_tables] or workspace.selected_table_ids
    try:
        if selected_tables:
            linking_result = linker.full_context(
                datasource_id=req.datasource_id,
                question=question,
                workspace_table_ids=workspace_ids,
                project_id=workspace.project_id,
            )
        else:
            linking_result = linker.link(
                datasource_id=req.datasource_id,
                question=question,
                workspace_table_ids=workspace.selected_table_ids or None,
                project_id=workspace.project_id,
            )
        schema_context = SchemaContextBuilder(db).build(linking_result)
        metadata = linking_result.response_metadata(schema_context)
        return {
            "mode": linking_result.mode,
            "schema_context": _compact_text(schema_context, MAX_CONTEXT_CHARS),
            "selected_tables": metadata.get("selectedTables", []),
            "selected_columns": metadata.get("selectedColumns", []),
            "schema_linking_reasons": metadata.get("schemaLinkingReasons", []),
            "semantic_aliases_used": metadata.get("semanticAliasesUsed", []),
            "workspace_scope_applied": metadata.get("workspaceScopeApplied", False),
            "workspace_scope_table_count": metadata.get("workspaceScopeTableCount", 0),
            "schema_context_size": metadata.get("schemaContextSize", 0),
            "original_schema_table_count": metadata.get("originalSchemaTableCount", 0),
            "selected_schema_table_count": metadata.get("selectedSchemaTableCount", 0),
        }
    except Exception as exc:
        return {
            "mode": "unavailable",
            "schema_context": "",
            "selected_tables": [str(table.table_name) for table in selected_tables],
            "selected_columns": [],
            "schema_linking_reasons": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _linking_question(req: AgentRunRequest, workspace: AgentWorkspaceContext) -> str:
    parts = [schema_linking_question(req)]
    if workspace.selected_sql:
        parts.append(workspace.selected_sql)
    elif workspace.active_sql:
        parts.append(workspace.active_sql)
    if workspace.last_error:
        parts.append(workspace.last_error)
    for table_name in workspace.selected_table_names[:MAX_TABLES]:
        parts.append(str(table_name))
    for column_ref in workspace.selected_column_refs[:32]:
        parts.append(str(column_ref))
    return _compact_text(" ".join(part for part in parts if part), 2200) or req.question


def _table_payload(table: SchemaTable) -> dict[str, Any]:
    columns = sorted(table.columns, key=lambda item: (item.ordinal_position or 0, str(item.column_name)))
    return {
        "id": table.id,
        "schema": table.table_schema,
        "name": table.table_name,
        "comment": table.table_comment,
        "type": table.table_type,
        "row_count_estimate": table.row_count_estimate,
        "columns": [
            {
                "id": column.id,
                "name": column.column_name,
                "data_type": column.data_type,
                "column_type": column.column_type,
                "nullable": bool(column.is_nullable),
                "primary_key": bool(column.is_primary_key),
                "foreign_key": bool(column.is_foreign_key),
                "comment": column.column_comment,
            }
            for column in columns[:MAX_COLUMNS_PER_TABLE]
        ],
        "truncated_columns": max(0, len(columns) - MAX_COLUMNS_PER_TABLE),
    }


def _semantic_context(
    db: Session,
    datasource_id: str,
    workspace: AgentWorkspaceContext,
) -> dict[str, Any]:
    aliases = (
        db.query(SemanticAlias)
        .filter(SemanticAlias.data_source_id == datasource_id)
        .order_by(SemanticAlias.created_at.desc())
        .limit(32)
        .all()
    )
    metrics = (
        db.query(SemanticMetric)
        .filter(SemanticMetric.data_source_id == datasource_id)
        .order_by(SemanticMetric.created_at.desc())
        .limit(32)
        .all()
    )
    dimensions = (
        db.query(SemanticDimension)
        .filter(SemanticDimension.data_source_id == datasource_id)
        .order_by(SemanticDimension.created_at.desc())
        .limit(32)
        .all()
    )
    scopes = []
    if workspace.project_id:
        scopes = (
            db.query(WorkspaceTableScope)
            .filter(
                WorkspaceTableScope.project_id == workspace.project_id,
                WorkspaceTableScope.data_source_id == datasource_id,
                WorkspaceTableScope.enabled == True,
            )
            .limit(64)
            .all()
        )
    return {
        "aliases": [
            {"alias": item.alias, "target_type": item.target_type, "target": item.target, "description": item.description}
            for item in aliases
        ],
        "metrics": [
            {
                "name": item.name,
                "expression": item.expression,
                "source_columns_json": item.source_columns_json,
                "description": item.description,
            }
            for item in metrics
        ],
        "dimensions": [
            {
                "name": item.name,
                "column_ref": item.column_ref,
                "transform": item.transform,
                "description": item.description,
            }
            for item in dimensions
        ],
        "table_scope": [
            {"table_id": item.table_id, "enabled": bool(item.enabled)}
            for item in scopes
        ],
        "client": dict(workspace.semantic_context or {}),
    }


def _selected_artifact_payload(
    db: Session,
    req: AgentRunRequest,
    workspace: AgentWorkspaceContext,
) -> dict[str, Any] | None:
    artifact_id = workspace.selected_artifact_id
    if not artifact_id:
        return None
    for artifact in (req.follow_up_context.artifacts if req.follow_up_context else []):
        if artifact.id == artifact_id:
            return _context_artifact_payload(artifact)
    record = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.id == artifact_id).first()
    if record is None:
        return None
    return {
        "id": record.id,
        "run_id": record.run_id,
        "type": record.type,
        "title": record.title,
        "payload": _safe_json(cast(str | None, record.payload_json)),
    }


def _context_artifact_payload(artifact: AgentContextArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "type": artifact.type,
        "title": artifact.title,
        "summary": artifact.summary,
        "payload": artifact.payload,
    }


def _recent_run_summary(
    db: Session,
    req: AgentRunRequest,
    workspace: AgentWorkspaceContext,
) -> dict[str, Any] | None:
    run = None
    if workspace.recent_agent_run_id:
        run = db.query(AgentRun).filter(AgentRun.id == workspace.recent_agent_run_id).first()
    if run is None:
        run = (
            db.query(AgentRun)
            .filter(AgentRun.datasource_id == req.datasource_id)
            .order_by(AgentRun.created_at.desc())
            .first()
        )
    if run is None:
        return None
    return {
        "run_id": run.id,
        "session_id": run.session_id,
        "parent_run_id": run.parent_run_id,
        "question": run.question,
        "status": run.status,
        "current_step_name": run.current_step_name,
        "context_summary": _compact_text(cast(str | None, run.context_summary), 800),
        "error": _compact_text(cast(str | None, run.error), 800),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _context_summary(bundle: dict[str, Any]) -> str:
    datasource_value = bundle.get("datasource")
    workspace_value = bundle.get("workspace")
    linking_value = bundle.get("schema_linking")
    datasource: dict[str, Any] = datasource_value if isinstance(datasource_value, dict) else {}
    workspace: dict[str, Any] = workspace_value if isinstance(workspace_value, dict) else {}
    linking: dict[str, Any] = linking_value if isinstance(linking_value, dict) else {}
    pieces = [
        f"Datasource {datasource.get('name') or datasource.get('id')} ({datasource.get('database_name') or datasource.get('db_type')})",
    ]
    selected_tables_value = workspace.get("selected_table_names") or linking.get("selected_tables") or []
    selected_tables: list[Any] = selected_tables_value if isinstance(selected_tables_value, list) else []
    if selected_tables:
        pieces.append(f"selected tables: {', '.join(str(item) for item in selected_tables[:MAX_TABLES])}")
    if workspace.get("active_sql"):
        pieces.append("active SQL available")
    if workspace.get("selected_sql"):
        pieces.append("selected SQL available")
    if workspace.get("last_query_result_preview"):
        pieces.append("last result preview available")
    if workspace.get("last_error"):
        pieces.append("last error available")
    if bundle.get("selected_artifact"):
        pieces.append("selected artifact available")
    return _compact_text("; ".join(pieces), 1000) or ""


def _preview_result(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    columns_value = value.get("columns")
    rows_value = value.get("rows")
    columns: list[Any] = columns_value if isinstance(columns_value, list) else []
    rows: list[Any] = rows_value if isinstance(rows_value, list) else []
    return {
        "success": value.get("success"),
        "columns": [str(column) for column in columns[:64]],
        "rows": [dict(row) for row in rows[:MAX_RESULT_ROWS] if isinstance(row, dict)],
        "rowCount": value.get("rowCount", len(rows)),
        "latencyMs": value.get("latencyMs"),
        "warnings": _safe_json_list(value.get("warnings"), limit=16),
        "truncated": bool(value.get("truncated")) if "truncated" in value else len(rows) > MAX_RESULT_ROWS,
    }


def _preview_sql_tabs(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tabs = []
    for tab in value[:12]:
        if not isinstance(tab, dict):
            continue
        tabs.append(
            {
                "id": tab.get("id"),
                "title": tab.get("title"),
                "active": bool(tab.get("active")),
                "sql": _compact_text(str(tab.get("sql") or ""), 1200),
            }
        )
    return tabs


def _safe_json_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _safe_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _compact_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."
