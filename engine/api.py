import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.ai import generate_sql
from engine.crypto import encrypt_password
from engine.datasource import build_mysql_ssl_params, test_connection
from engine.db import get_db
from engine.errors import DataBoxError
from engine.executor import execute_query
from engine.guardrail import guardrail_check
from engine.models import DataSource, QueryHistory, SchemaTable, GoldenSQL, LLMLog
from engine.query_registry import QUERY_REGISTRY
from engine.schema_sync import build_er_diagram_data, sync_schema

logger = logging.getLogger("databox.api")
router = APIRouter(prefix="/api/v1")


class DataSourceTestRequest(BaseModel):
    host: str
    port: int = 3306
    database_name: str
    username: str
    password: str

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True


class DataSourceCreateRequest(BaseModel):
    name: str
    host: str
    port: int = 3306
    database_name: str
    username: str
    password: str
    connection_mode: str = "direct"
    is_read_only: bool = False
    env: str = "dev"

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True


class SQLValidateRequest(BaseModel):
    sql: str


class SQLExecuteRequest(BaseModel):
    datasource_id: str
    sql: str
    question: str | None = None
    execution_id: str | None = None


class SQLCancelRequest(BaseModel):
    execution_id: str


class SQLGenerateRequest(BaseModel):
    datasource_id: str
    question: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False



def _datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "name": ds.name,
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "connection_mode": ds.connection_mode,
        "is_read_only": bool(ds.is_read_only),
        "env": ds.env or "dev",
        "status": ds.status,
        "ssh_enabled": bool(ds.ssh_enabled),
        "ssh_host": ds.ssh_host or "",
        "ssh_port": ds.ssh_port or 22,
        "ssh_username": ds.ssh_username or "",
        "ssh_pkey_path": ds.ssh_pkey_path or "",
        "ssl_enabled": bool(ds.ssl_enabled),
        "ssl_ca_path": ds.ssl_ca_path or "",
        "ssl_cert_path": ds.ssl_cert_path or "",
        "ssl_key_path": ds.ssl_key_path or "",
        "ssl_verify_identity": bool(ds.ssl_verify_identity),
        "last_test_at": ds.last_test_at.isoformat() if ds.last_test_at else None,
        "last_test_status": ds.last_test_status,
        "last_test_error": ds.last_test_error,
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


@router.post("/datasources/test")
def api_test_connection(req: DataSourceTestRequest) -> dict[str, Any]:
    try:
        return test_connection(req.model_dump())
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("Connection test failed")
        raise HTTPException(status_code=400, detail={"code": "CONNECTION_FAILED", "message": "数据库连接测试失败，请检查连接配置。"})


@router.post("/datasources")
def api_create_datasource(req: DataSourceCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        build_mysql_ssl_params(req.model_dump())
        cipher, nonce = encrypt_password(req.password)

        ssh_password_ciphertext = ""
        ssh_password_nonce = ""
        if req.ssh_password:
            ssh_password_ciphertext, ssh_password_nonce = encrypt_password(req.ssh_password)

        ssh_pkey_passphrase_ciphertext = ""
        ssh_pkey_passphrase_nonce = ""
        if req.ssh_pkey_passphrase:
            ssh_pkey_passphrase_ciphertext, ssh_pkey_passphrase_nonce = encrypt_password(req.ssh_pkey_passphrase)

        datasource = DataSource(
            id=str(uuid.uuid4()),
            name=req.name,
            host=req.host,
            port=req.port,
            database_name=req.database_name,
            username=req.username,
            password_ciphertext=cipher,
            password_nonce=nonce,
            ssh_enabled=req.ssh_enabled,
            ssh_host=req.ssh_host,
            ssh_port=req.ssh_port,
            ssh_username=req.ssh_username,
            ssh_password_ciphertext=ssh_password_ciphertext,
            ssh_password_nonce=ssh_password_nonce,
            ssh_pkey_path=req.ssh_pkey_path,
            ssh_pkey_passphrase_ciphertext=ssh_pkey_passphrase_ciphertext,
            ssh_pkey_passphrase_nonce=ssh_pkey_passphrase_nonce,
            ssl_enabled=req.ssl_enabled,
            ssl_ca_path=req.ssl_ca_path,
            ssl_cert_path=req.ssl_cert_path,
            ssl_key_path=req.ssl_key_path,
            ssl_verify_identity=req.ssl_verify_identity,
            connection_mode=req.connection_mode,
            is_read_only=req.is_read_only,
            env=req.env,
            status="active",
        )
        db.add(datasource)
        db.commit()
        db.refresh(datasource)
        return _datasource_to_dict(datasource)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create datasource")
        raise HTTPException(
            status_code=500,
            detail={"code": "DATASOURCE_CREATE_FAILED", "message": "创建数据源失败，请稍后重试。"},
        )


@router.get("/datasources")
def api_list_datasources(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [_datasource_to_dict(ds) for ds in db.query(DataSource).all()]


@router.delete("/datasources/{id}")
def api_delete_datasource(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "数据源不存在"})

    try:
        from engine.datasource import close_active_tunnel
        close_active_tunnel(id)

        db.delete(datasource)
        db.commit()
        return {"success": True, "message": "数据源已删除"}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete datasource")
        raise HTTPException(
            status_code=500,
            detail={"code": "DATASOURCE_DELETE_FAILED", "message": "删除数据源失败，请稍后重试。"},
        )


@router.post("/datasources/{id}/sync")
def api_sync_schema(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return sync_schema(db, id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "SYNC_FAILED", "message": str(exc)})
    except Exception as exc:
        logger.exception("Schema sync failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "SYNC_FAILED", "message": "元数据结构同步失败，请检查数据库连接后重试。"},
        )


@router.get("/schema/tables")
def api_list_tables(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()
    return [
        {
            "id": table.id,
            "table_name": table.table_name,
            "table_comment": table.table_comment or "",
            "table_type": table.table_type,
            "row_count_estimate": table.row_count_estimate,
            "columns_count": len(table.columns),
        }
        for table in tables
    ]


@router.get("/schema/tables/{table_id}/columns")
def api_list_columns(table_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "表结构记录不存在"})

    return [
        {
            "id": column.id,
            "column_name": column.column_name,
            "data_type": column.data_type,
            "column_type": column.column_type,
            "is_nullable": bool(column.is_nullable),
            "column_default": column.column_default or "",
            "column_comment": column.column_comment or "",
            "is_primary_key": bool(column.is_primary_key),
            "is_foreign_key": bool(column.is_foreign_key),
            "foreign_table_id": column.foreign_table_id,
            "foreign_column_id": column.foreign_column_id,
        }
        for column in table.columns
    ]


@router.get("/schema/er-diagram")
def api_get_er_diagram(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return build_er_diagram_data(db, datasource_id)
    except Exception as exc:
        logger.exception("ER diagram build failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "DIAGRAM_FAILED", "message": "生成 ER 图失败，请确认已完成 Schema 同步。"},
        )


@router.post("/query/validate")
def api_validate_sql(req: SQLValidateRequest) -> dict[str, Any]:
    result = guardrail_check(req.sql)
    return dict(result)


@router.post("/query/execute")
def api_execute_sql(req: SQLExecuteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return execute_query(db, req.datasource_id, req.sql, req.question, req.execution_id)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL execution failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "EXECUTION_ERROR", "message": "SQL 执行失败，请检查语句是否正确。"},
        )


class SQLExplainRequest(BaseModel):
    datasource_id: str
    sql: str


@router.post("/query/explain")
def api_explain_sql(req: SQLExplainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from engine.executor import explain_sql
        return explain_sql(db, req.datasource_id, req.sql)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL explain failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "EXPLAIN_ERROR", "message": f"SQL EXPLAIN 诊断失败: {str(exc)}"},
        )


@router.post("/query/cancel")
def api_cancel_sql(req: SQLCancelRequest) -> dict[str, Any]:
    return QUERY_REGISTRY.cancel(req.execution_id)


@router.get("/query/history")
def api_query_history(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    history = (
        db.query(QueryHistory)
        .filter(QueryHistory.data_source_id == datasource_id)
        .order_by(QueryHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": item.id,
            "question": item.question or "",
            "submitted_sql": item.submitted_sql,
            "generated_sql": item.generated_sql or "",
            "safe_sql": item.safe_sql or "",
            "executed_sql": item.executed_sql or "",
            "guardrail_result": item.guardrail_result,
            "guardrail_checks": item.guardrail_checks or "",
            "execution_status": item.execution_status,
            "execution_time_ms": item.execution_time_ms or 0,
            "rows_returned": item.rows_returned or 0,
            "columns_returned": item.columns_returned or 0,
            "error_message": item.error_message or "",
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in history
    ]


@router.post("/query/generate")
def api_generate_sql(req: SQLGenerateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        llm_config = {}
        if req.api_key:
            llm_config = {
                "api_key": req.api_key,
                "api_base": req.api_base or "https://api.openai.com/v1",
                "model": req.model_name or "gpt-4o-mini",
            }
        return generate_sql(db, req.datasource_id, req.question, llm_config, req.optimize_rag)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL generation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "GENERATION_ERROR", "message": "AI 生成 SQL 失败，请检查模型配置或稍后重试。"},
        )


class GoldenSQLCreateRequest(BaseModel):
    datasource_id: str
    question: str
    golden_sql: str


class BenchmarkRequest(BaseModel):
    datasource_id: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False


@router.get("/golden-sql")
def api_list_golden_sql(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    pairs = db.query(GoldenSQL).filter(GoldenSQL.data_source_id == datasource_id).order_by(GoldenSQL.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "data_source_id": p.data_source_id,
            "question": p.question,
            "golden_sql": p.golden_sql,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in pairs
    ]


@router.post("/golden-sql")
def api_create_golden_sql(req: GoldenSQLCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pair = GoldenSQL(
            id=str(uuid.uuid4()),
            data_source_id=req.datasource_id,
            question=req.question,
            golden_sql=req.golden_sql
        )
        db.add(pair)
        db.commit()
        db.refresh(pair)
        return {
            "id": pair.id,
            "data_source_id": pair.data_source_id,
            "question": pair.question,
            "golden_sql": pair.golden_sql,
            "created_at": pair.created_at.isoformat() if pair.created_at else None
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create golden sql")
        raise HTTPException(status_code=500, detail="保存 Golden SQL 失败")


@router.delete("/golden-sql/{id}")
def api_delete_golden_sql(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    pair = db.query(GoldenSQL).filter(GoldenSQL.id == id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Golden SQL 不存在")
    try:
        db.delete(pair)
        db.commit()
        return {"success": True, "message": "Golden SQL 已删除"}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete golden sql")
        raise HTTPException(status_code=500, detail="删除 Golden SQL 失败")


@router.post("/golden-sql/run-benchmark")
def api_run_benchmark(req: BenchmarkRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    import re
    pairs = db.query(GoldenSQL).filter(GoldenSQL.data_source_id == req.datasource_id).all()
    if not pairs:
        return {
            "success": True,
            "total_queries": 0,
            "passed_count": 0,
            "accuracy_rate": 0.0,
            "avg_latency_ms": 0.0,
            "details": []
        }

    total_queries = len(pairs)
    passed_count = 0
    total_latency = 0
    details = []

    llm_config = {}
    if req.api_key:
        llm_config = {
            "api_key": req.api_key,
            "api_base": req.api_base or "https://api.openai.com/v1",
            "model": req.model_name or "gpt-4o-mini",
        }

    for p in pairs:
        # Step 1: AI Generation
        gen_sql = ""
        latency = 0
        error_msg = ""
        try:
            res = generate_sql(db, req.datasource_id, p.question, llm_config, req.optimize_rag)
            gen_sql = res["sql"]
            latency = res["latencyMs"]
            total_latency += latency
        except Exception as e:
            error_msg = f"SQL 生成失败: {str(e)}"
            details.append({
                "golden_id": p.id,
                "question": p.question,
                "golden_sql": p.golden_sql,
                "generated_sql": "",
                "status": "failed",
                "match_type": "none",
                "latency_ms": 0,
                "error_message": error_msg
            })
            continue

        # Step 2: Compare
        clean_golden = re.sub(r"\s+", " ", p.golden_sql.strip().lower().replace(";", ""))
        clean_gen = re.sub(r"\s+", " ", gen_sql.strip().lower().replace(";", ""))

        if clean_golden == clean_gen:
            passed_count += 1
            details.append({
                "golden_id": p.id,
                "question": p.question,
                "golden_sql": p.golden_sql,
                "generated_sql": gen_sql,
                "status": "passed",
                "match_type": "lexical",
                "latency_ms": latency,
                "error_message": ""
            })
            continue

        # Execution comparison
        try:
            gold_res = execute_query(db, req.datasource_id, p.golden_sql, question=None)
            gen_res = execute_query(db, req.datasource_id, gen_sql, question=None)

            if gold_res.get("success") and gen_res.get("success"):
                gold_rows = gold_res.get("rows", [])
                gen_rows = gen_res.get("rows", [])

                if len(gold_rows) == len(gen_rows):
                    if gold_rows == gen_rows:
                        passed_count += 1
                        details.append({
                            "golden_id": p.id,
                            "question": p.question,
                            "golden_sql": p.golden_sql,
                            "generated_sql": gen_sql,
                            "status": "passed",
                            "match_type": "execution",
                            "latency_ms": latency,
                            "error_message": ""
                        })
                        continue

            details.append({
                "golden_id": p.id,
                "question": p.question,
                "golden_sql": p.golden_sql,
                "generated_sql": gen_sql,
                "status": "failed",
                "match_type": "none",
                "latency_ms": latency,
                "error_message": "语法与执行数据集不一致"
            })

        except Exception as exec_err:
            details.append({
                "golden_id": p.id,
                "question": p.question,
                "golden_sql": p.golden_sql,
                "generated_sql": gen_sql,
                "status": "failed",
                "match_type": "none",
                "latency_ms": latency,
                "error_message": f"执行对比出错: {str(exec_err)}"
            })

    avg_latency = round(total_latency / total_queries, 2) if total_queries > 0 else 0.0
    accuracy = round((passed_count / total_queries) * 100, 2) if total_queries > 0 else 0.0

    return {
        "success": True,
        "total_queries": total_queries,
        "passed_count": passed_count,
        "accuracy_rate": accuracy,
        "avg_latency_ms": avg_latency,
        "details": details
    }


@router.get("/llm-logs/stats")
def api_get_llm_stats(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    logs = db.query(LLMLog).filter(LLMLog.data_source_id == datasource_id).all()
    
    total_calls = len(logs)
    success_count = sum(1 for log in logs if log.status == "success")
    failed_count = total_calls - success_count
    
    success_rate = round((success_count / total_calls) * 100, 2) if total_calls > 0 else 100.0
    avg_latency = round(sum(log.latency_ms or 0 for log in logs) / total_calls, 2) if total_calls > 0 else 0.0
    
    histories = db.query(QueryHistory).filter(QueryHistory.data_source_id == datasource_id).all()
    total_queries = len(histories)
    blocked_count = sum(1 for h in histories if h.guardrail_result == "reject")
    approved_count = total_queries - blocked_count
    
    guardrail_block_rate = round((blocked_count / total_queries) * 100, 2) if total_queries > 0 else 0.0

    from collections import defaultdict
    date_counts = defaultdict(int)
    for log in logs:
        if log.created_at:
            date_str = log.created_at.strftime("%m-%d")
            date_counts[date_str] += 1
            
    sorted_dates = sorted(date_counts.keys())[-7:]
    chart_data = [{"date": d, "value": date_counts[d]} for d in sorted_dates]

    model_counts = defaultdict(int)
    for log in logs:
        if log.model_name:
            model_counts[log.model_name] += 1
    model_dist = [{"name": name, "value": count} for name, count in model_counts.items()]

    return {
        "total_calls": total_calls,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency,
        "guardrail_total": total_queries,
        "guardrail_blocked": blocked_count,
        "guardrail_approved": approved_count,
        "guardrail_block_rate": guardrail_block_rate,
        "chart_data": chart_data,
        "model_dist": model_dist
    }


@router.post("/demo/start")
def api_start_demo_mysql(db: Session = Depends(get_db)) -> dict[str, Any]:
    from engine.demo_mysql import (
        check_docker_available,
        launch_demo_container,
        wait_for_mysql_port,
        populate_demo_data
    )

    if not check_docker_available():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_NOT_AVAILABLE",
                "message": "未检测到本地 Docker 运行环境，请确保 Docker Desktop 已启动且加入了系统 PATH 环境变量。"
            }
        )

    try:
        launch_demo_container()
    except Exception as e:
        logger.exception("Failed to launch demo container")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_LAUNCH_FAILED",
                "message": f"创建并启动 Docker 容器失败: {str(e)}"
            }
        )

    if not wait_for_mysql_port(timeout=45):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_WAIT_TIMEOUT",
                "message": "等待 Docker MySQL 实例就绪超时，请检查 Docker 中 databox-demo-mysql 容器的日志。"
            }
        )

    try:
        populate_demo_data()
    except Exception as e:
        logger.exception("Failed to seed demo database")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_SEED_FAILED",
                "message": f"数据库表结构及电商演示数据导入失败: {str(e)}"
            }
        )

    # Register datasource in local SQLite
    datasource = db.query(DataSource).filter(
        DataSource.host == "127.0.0.1",
        DataSource.port == 3309,
        DataSource.database_name == "databox_demo"
    ).first()

    if not datasource:
        try:
            cipher, nonce = encrypt_password("demo_pass")
            datasource = DataSource(
                id=str(uuid.uuid4()),
                name="本地 Demo 电子商务数据库 (Docker)",
                host="127.0.0.1",
                port=3309,
                database_name="databox_demo",
                username="databox_demo_user",
                password_ciphertext=cipher,
                password_nonce=nonce,
                is_read_only=False,
                env="dev",
                status="active"
            )
            db.add(datasource)
            db.commit()
            db.refresh(datasource)
        except Exception as e:
            db.rollback()
            logger.exception("Failed to register demo datasource in db")
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "DATASOURCE_REGISTER_FAILED",
                    "message": f"自动注册 Demo 数据源失败: {str(e)}"
                }
            )

    # Sync Schema metadata
    try:
        sync_schema(db, datasource.id)
    except Exception as e:
        logger.exception("Failed to sync demo database schema")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_FAILED",
                "message": f"自动同步表元数据结构失败: {str(e)}。但数据库连接已保存，您可以手动同步。"
            }
        )

    return _datasource_to_dict(datasource)

