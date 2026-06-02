import logging
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from engine.agent import AgentRunRequest, AgentRunResponse, AgentRuntimeEvent, DataBoxAgentRuntime
from engine.ai import generate_sql
from engine.db import get_db
from engine.errors import DataBoxError
from engine.models import GoldenSQL, LLMLog, QueryHistory
from engine.schemas import (
    SQLGenerateRequest,
    GoldenSQLCreateRequest,
    BenchmarkRequest,
)
from engine.executor import execute_query

logger = logging.getLogger("databox.api.ai")
router = APIRouter()


@router.post("/query/agent-run", response_model=AgentRunResponse)
def api_agent_run(req: AgentRunRequest, db: Session = Depends(get_db)) -> AgentRunResponse:
    try:
        return DataBoxAgentRuntime(db).run(req)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("Agent runtime failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "AGENT_RUNTIME_ERROR", "message": f"Agent runtime failed: {str(exc)}"},
        )


def _format_sse_event(event: AgentRuntimeEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


@router.post("/query/agent-run/stream")
def api_agent_run_stream(req: AgentRunRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    def stream_events():
        try:
            for event in DataBoxAgentRuntime(db).run_iter(req):
                yield _format_sse_event(event)
        except DataBoxError as exc:
            payload = {
                "event_id": "runtime_error_databox",
                "run_id": "",
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": str(exc),
                "response": None,
                "code": exc.code,
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:
            logger.exception("Agent runtime stream failed")
            payload = {
                "event_id": "runtime_error_unhandled",
                "run_id": "",
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": f"Agent runtime failed: {str(exc)}",
                "response": None,
                "code": "AGENT_RUNTIME_ERROR",
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
            detail={"code": "GENERATION_ERROR", "message": f"AI 生成 SQL 失败: {str(exc)}"},
        )


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
            res = generate_sql(db, req.datasource_id, str(p.question), llm_config, req.optimize_rag)
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
            gold_res = execute_query(db, req.datasource_id, str(p.golden_sql), question=None)
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
    date_counts: dict[str, int] = defaultdict(int)
    for log in logs:
        if log.created_at:
            date_str = log.created_at.strftime("%m-%d")
            date_counts[date_str] += 1
            
    sorted_dates = sorted(date_counts.keys())[-7:]
    chart_data = [{"date": d, "value": date_counts[d]} for d in sorted_dates]

    model_counts: dict[str, int] = defaultdict(int)
    for log in logs:
        if log.model_name:
            model_counts[str(log.model_name)] += 1
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
