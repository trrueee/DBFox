from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from engine.api.datasources.common import schema_column_to_dict, schema_table_to_dict
from engine.app.errors import public_message
from engine.db import get_db
from engine.environment.schema_catalog_sync import ensure_catalog as _sync_catalog
from engine.errors import DBFoxError, NotFoundError
from engine.models import SchemaTable
from engine.schema_sync import build_er_diagram_data

logger = logging.getLogger("dbfox.api.datasources.schema")
router = APIRouter()


class SchemaSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_enrich: bool = False
    llm_credential_id: str | None = None
    api_base: str | None = None
    model_name: str | None = None


def load_schema_tables(db: Session, datasource_id: str) -> list[SchemaTable]:
    return db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()


@router.post("/datasources/{id}/sync")
def api_sync_schema(
    id: str,
    req: SchemaSyncRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        payload = req or SchemaSyncRequest()
        result = _sync_catalog(
            db,
            id,
            ai_enrich=payload.ai_enrich,
            llm_credential_id=payload.llm_credential_id,
            ai_api_base=payload.api_base,
            ai_model_name=payload.model_name,
        )

        response: dict[str, Any] = {
            "ok": result.synced,
            "tablesSynced": (result.tables_created or 0) + (result.tables_updated or 0),
            "tablesDropped": result.tables_removed or 0,
            "columnsCreated": result.columns_created or 0,
            "columnsUpdated": result.columns_updated or 0,
            "columnsRemoved": result.columns_removed or 0,
            "message": (
                f"Synced: {result.tables_created or 0} created, "
                f"{result.tables_updated or 0} updated, {result.tables_removed or 0} removed."
            ),
        }

        if payload.ai_enrich:
            enrich = result.ai_enrich_result or {
                "ai_enriched": False,
                "enriched_count": 0,
                "reason": "AI enrichment did not return a result.",
            }
            response["aiEnrich"] = (
                enrich.model_dump(mode="json") if hasattr(enrich, "model_dump") else dict(enrich or {})
            )

        return response
    except ValueError as exc:
        raise DBFoxError(code="SYNC_FAILED", message=str(exc)) from exc


@router.get("/schema/tables")
def api_list_tables(
    datasource_id: str = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tables = load_schema_tables(db, datasource_id)
    if not tables:
        try:
            _sync_catalog(db, datasource_id)
        except Exception as exc:
            db.rollback()
            logger.warning("Auto schema sync before listing tables failed for %s", datasource_id)
            raise DBFoxError(
                message=f"Schema sync failed: {public_message(exc)}",
                code="SYNC_FAILED",
            ) from exc
        else:
            tables = load_schema_tables(db, datasource_id)
    return [schema_table_to_dict(table) for table in tables]


@router.get("/schema/tables/{table_id}/columns")
def api_list_columns(table_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id).first()
    if not table:
        raise NotFoundError("表结构记录不存在")

    return [schema_column_to_dict(column) for column in table.columns]


@router.get("/schema/er-diagram")
def api_get_er_diagram(
    datasource_id: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return build_er_diagram_data(db, datasource_id)
    except Exception:
        logger.exception("ER diagram build failed")
        raise
