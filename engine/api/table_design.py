import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DataBoxError
from engine.models import DataSource, TableDesignDraft
from engine.schemas import (
    SchemaAlterationRequest,
    TableDesignDDLRequest,
    TableDesignExecuteRequest,
    TableDesignDraftSaveRequest,
    TableDesignAIRequest,
    TestDataGenerateRequest,
)
from engine.table_design import generate_create_table_ddl
from engine.policy.engine import PolicyEngine

logger = logging.getLogger("databox.api.table_design")
router = APIRouter()


def _draft_to_dict(draft: TableDesignDraft) -> dict[str, Any]:
    try:
        cols = json.loads(str(draft.columns_json))
    except Exception:
        cols = []
    try:
        idxs = json.loads(str(draft.indexes_json))
    except Exception:
        idxs = []
    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "table_name": draft.table_name,
        "table_comment": draft.table_comment or "",
        "columns": cols,
        "indexes": idxs,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


@router.post("/schema/design/ai-modify")
def api_generate_schema_alteration(req: SchemaAlterationRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from engine.sql.generator import generate_schema_alteration_ai
        llm_config = {
            "api_key": req.api_key,
            "api_base": req.api_base,
            "model": req.model
        }
        return generate_schema_alteration_ai(db, req.datasource_id, req.instruction, llm_config)
    except Exception as exc:
        logger.exception("AI Schema alteration DDL generation failed")
        raise HTTPException(status_code=500, detail={"code": "AI_MODIFY_FAILED", "message": f"AI 批注式修改失败: {str(exc)}"})


@router.post("/schema/design/create-table-ddl")
def api_generate_create_table_ddl(req: TableDesignDDLRequest) -> dict[str, Any]:
    try:
        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        return generate_create_table_ddl(payload)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception:
        logger.exception("Create-table DDL generation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "TABLE_DESIGN_FAILED", "message": "生成建表 SQL 失败，请检查表结构草稿。"},
        )


@router.post("/schema/design/execute-ddl")
def api_execute_table_design_ddl(req: TableDesignExecuteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "数据源不存在"})

    # 🔒 Policy Engine Enforcement for DDL Execution
    try:
        PolicyEngine.enforce_ddl_policy(datasource)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})

    # 🔒 Two-Phase confirmation check for dangerous DDL operations
    from engine.policy import confirmation_bypass_enabled, sha256_hash, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"ddl_hash": sha256_hash(req.ddl)}
        if not req.confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=req.datasource_id,
                action="execute_ddl",
                details=expected_details,
                expected_confirm_text=str(datasource.name)
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将在数据源 '{datasource.name}' 上执行以下结构变更 DDL：\n\n{req.ddl}\n\n该操作无法撤销！请输入数据源名称以确认执行。",
                "expected_confirm_text": datasource.name
            }
        else:
            is_valid, err_msg = confirmation_manager.validate_and_consume(
                req.confirm_token,
                req.confirm_text or "",
                expected_action="execute_ddl",
                expected_datasource_id=req.datasource_id,
                expected_details=expected_details
            )
            if not is_valid:
                raise HTTPException(status_code=400, detail={"code": "CONFIRMATION_FAILED", "message": err_msg})

    try:
        from engine.table_design import execute_table_design_ddl
        return execute_table_design_ddl(db, req.datasource_id, req.ddl)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("Execute table design DDL failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "TABLE_DESIGN_FAILED", "message": f"执行建表 SQL 失败: {str(exc)}"},
        )


@router.get("/schema/design/drafts")
def api_list_table_design_drafts(project_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    drafts = db.query(TableDesignDraft).filter(TableDesignDraft.project_id == project_id).order_by(TableDesignDraft.updated_at.desc()).all()
    return [_draft_to_dict(d) for d in drafts]


@router.get("/schema/design/drafts/{draft_id}")
def api_get_table_design_draft(draft_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    draft = db.query(TableDesignDraft).filter(TableDesignDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "设计草稿不存在"})
    return _draft_to_dict(draft)


@router.post("/schema/design/drafts/save")
def api_save_table_design_draft(req: TableDesignDraftSaveRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        columns_data = [col.model_dump() if hasattr(col, "model_dump") else col.dict() for col in req.columns]
        indexes_data = [idx.model_dump() if hasattr(idx, "model_dump") else idx.dict() for idx in req.indexes]
        cols_json = json.dumps(columns_data)
        idxs_json = json.dumps(indexes_data)

        if req.draft_id:
            draft = db.query(TableDesignDraft).filter(TableDesignDraft.id == req.draft_id).first()
            if not draft:
                raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "设计草稿不存在"})
            draft.table_name = req.table_name  # type: ignore[assignment]
            draft.table_comment = req.table_comment  # type: ignore[assignment]
            draft.columns_json = cols_json  # type: ignore[assignment]
            draft.indexes_json = idxs_json  # type: ignore[assignment]
        else:
            draft = TableDesignDraft(
                id=str(uuid.uuid4()),
                project_id=req.project_id,
                table_name=req.table_name,
                table_comment=req.table_comment,
                columns_json=cols_json,
                indexes_json=idxs_json
            )
            db.add(draft)

        db.commit()
        db.refresh(draft)
        return _draft_to_dict(draft)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save table design draft")
        raise HTTPException(
            status_code=500,
            detail={"code": "DRAFT_SAVE_FAILED", "message": f"保存设计草稿失败: {str(exc)}"}
        )


@router.delete("/schema/design/drafts/{draft_id}")
def api_delete_table_design_draft(draft_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    draft = db.query(TableDesignDraft).filter(TableDesignDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "设计草稿不存在"})
    try:
        db.delete(draft)
        db.commit()
        return {"success": True, "message": "设计草稿已删除"}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete table design draft")
        raise HTTPException(
            status_code=500,
            detail={"code": "DRAFT_DELETE_FAILED", "message": f"删除设计草稿失败: {str(exc)}"}
        )


@router.post("/schema/design/ai-generate")
def api_generate_table_design_ai(req: TableDesignAIRequest) -> dict[str, Any]:
    try:
        from engine.sql.generator import generate_table_design_ai
        llm_config = {}
        if req.api_key:
            llm_config = {
                "api_key": req.api_key,
                "api_base": req.api_base or "https://api.openai.com/v1",
                "model": req.model_name or "gpt-4o-mini"
            }
        return generate_table_design_ai(req.prompt, llm_config)
    except Exception as exc:
        logger.exception("AI table design generation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "AI_DESIGN_FAILED", "message": f"AI 辅助设计生成失败: {str(exc)}"}
        )


@router.post("/schema/generate-test-data")
def api_generate_test_data(req: TestDataGenerateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "数据源不存在"})

    # 🔒 Policy Engine Enforcement for Test Data Generation
    try:
        PolicyEngine.enforce_test_data_policy(datasource)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})

    # 🔒 Two-Phase confirmation check for test data generation
    from engine.policy import confirmation_bypass_enabled, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"table_name": req.table_name, "row_count": req.row_count}
        if not req.confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=req.datasource_id,
                action="generate_test_data",
                details=expected_details,
                expected_confirm_text=str(datasource.name)
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将在数据源 '{datasource.name}' 的表 '{req.table_name}' 上批量生成 {req.row_count} 条智能测试数据。\n\n这会向该表插入大量模拟行！请输入数据源名称以确认执行。",
                "expected_confirm_text": datasource.name
            }
        else:
            is_valid, err_msg = confirmation_manager.validate_and_consume(
                req.confirm_token,
                req.confirm_text or "",
                expected_action="generate_test_data",
                expected_datasource_id=req.datasource_id,
                expected_details=expected_details
            )
            if not is_valid:
                raise HTTPException(status_code=400, detail={"code": "CONFIRMATION_FAILED", "message": err_msg})

    try:
        from engine.test_data import generate_smart_test_data
        return generate_smart_test_data(
            db=db,
            datasource_id=req.datasource_id,
            table_name=req.table_name,
            row_count=req.row_count,
            language=req.language
        )
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("AI test data generation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "TEST_DATA_FAILED", "message": f"智能测试数据生成失败: {str(exc)}"}
        )
