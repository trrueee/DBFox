from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.api.datasources.common import schema_column_to_dict, schema_table_to_dict, set_model_attr
from engine.db import get_db
from engine.errors import DBFoxError, NotFoundError
from engine.models import SchemaColumn, SchemaTable

router = APIRouter()


class TableMetadataUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ai_description: str | None = Field(default=None, max_length=2000)
    semantic_tags: str | None = Field(default=None, max_length=1000)
    business_terms: str | None = Field(default=None, max_length=1000)
    subject_area: str | None = Field(default=None, max_length=128)
    ai_confidence: float | None = Field(default=None, ge=0, le=1)


class ColumnMetadataUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ai_description: str | None = Field(default=None, max_length=2000)
    semantic_tags: str | None = Field(default=None, max_length=1000)
    business_terms: str | None = Field(default=None, max_length=1000)
    ai_confidence: float | None = Field(default=None, ge=0, le=1)


@router.put("/schema/tables/{table_id}")
def api_update_table_metadata(
    table_id: str,
    req: TableMetadataUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id).first()
    if not table:
        raise NotFoundError("表结构记录不存在")

    if req.ai_description is not None:
        set_model_attr(table, "ai_description", req.ai_description)
    if req.semantic_tags is not None:
        set_model_attr(table, "semantic_tags", req.semantic_tags)
    if req.business_terms is not None:
        set_model_attr(table, "business_terms", req.business_terms)
    if req.subject_area is not None:
        set_model_attr(table, "subject_area", req.subject_area)
    if req.ai_confidence is not None:
        set_model_attr(table, "ai_confidence", req.ai_confidence)

    try:
        db.commit()
        db.refresh(table)
        return {"success": True, "table": schema_table_to_dict(table)}
    except Exception as exc:
        db.rollback()
        raise DBFoxError(code="UPDATE_FAILED", message=str(exc)) from exc


@router.put("/schema/columns/{column_id}")
def api_update_column_metadata(
    column_id: str,
    req: ColumnMetadataUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    column = db.query(SchemaColumn).filter(SchemaColumn.id == column_id).first()
    if not column:
        raise NotFoundError("字段结构记录不存在")

    if req.ai_description is not None:
        set_model_attr(column, "ai_description", req.ai_description)
    if req.semantic_tags is not None:
        set_model_attr(column, "semantic_tags", req.semantic_tags)
    if req.business_terms is not None:
        set_model_attr(column, "business_terms", req.business_terms)
    if req.ai_confidence is not None:
        set_model_attr(column, "ai_confidence", req.ai_confidence)

    try:
        db.commit()
        db.refresh(column)
        return {"success": True, "column": schema_column_to_dict(column)}
    except Exception as exc:
        db.rollback()
        raise DBFoxError(code="UPDATE_FAILED", message=str(exc)) from exc
