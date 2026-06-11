from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Any

import httpx
import sqlglot
from sqlglot import exp
from sqlalchemy.orm import Session

from engine.errors import AIServiceError
from engine.models import DataSource, LLMLog, SchemaColumn, SchemaTable
from engine.semantic import QueryPlanBuilder, SchemaContextBuilder, SchemaLinker
from engine.sql.trust_gate import TrustGate


def _persist_llm_log(db, log_entry) -> None:
    """Write LLM log entry to DB if persistence is enabled."""
    if os.environ.get("AGENT_PERSISTENCE_MODE", "sync") == "disabled":
        return
    db.add(log_entry)
    db.commit()


def _has_real_llm_config(api_key: str | None, model_name: str | None) -> bool:
    return bool(api_key and model_name)


def _query_plan_requires_llm(query_plan: dict[str, Any] | None) -> bool:
    """Conservative heuristic: inspect a query_plan dict and detect anti-join, set logic, nested queries or explicit unsupported ops."""
    if not query_plan:
        return False
    raw = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan
    txt = str(raw).lower()
    markers = ("anti_join", "not exists", "not in", "intersect", "except", "set_logic", "nested", "nested_query", "having", "exists")
    if any(m in txt for m in markers):
        return True
    # also check intent/warnings
    intent = str(raw.get("intent") or "").lower()
    if intent in ("answer_question",) and raw.get("mode") == "offline":
        # if offline answer_question but plan contains only count metric and no projections, consider requiring LLM
        metrics = raw.get("metrics") or []
        dimensions = raw.get("dimensions") or []
        if metrics and not dimensions:
            # heuristic: metric expressions with count only
            if all("count" in str((m or {}).get("expression") or "").lower() for m in metrics if isinstance(m, dict)):
                return True
    return False


def select_relevant_tables(tables: list[SchemaTable], question: str) -> list[SchemaTable]:
    """
    RAG Heuristic: Selects the most relevant tables for the given question
    based on lexical overlap and relational linking.
    """
    q_words = re.findall(r"[\u4e00-\u9fa5\w]+", question.lower())
    if not q_words:
        return tables[:8] if len(tables) > 8 else tables

    scored_tables = []
    for t in tables:
        score = 0
        t_name_lower = t.table_name.lower()

        # 1. Exact match of table name
        if t_name_lower in question.lower():
            score += 15

        # 2. Name token overlap
        for word in q_words:
            if word in t_name_lower:
                score += 8

        # 3. Comment overlap
        if t.table_comment:
            comment_lower = t.table_comment.lower()
            for word in q_words:
                if word in comment_lower:
                    score += 5

        # 4. Column overlap
        for col in t.columns:
            col_name_lower = col.column_name.lower()
            if col_name_lower in question.lower():
                score += 3
            if col.column_comment:
                col_comment_lower = col.column_comment.lower()
                for word in q_words:
                    if word in col_comment_lower:
                        score += 2

        scored_tables.append((t, score))

    # Sort tables by score descending
    scored_tables.sort(key=lambda x: x[1], reverse=True)

    # Select tables with score > 0
    selected = [t for t, score in scored_tables if score > 0]
    if not selected:
        selected = [t for t, score in scored_tables[:5]]
    else:
        selected = selected[:6]

    # Enforce minimum size: if total tables <= 8, return all
    if len(tables) <= 8:
        return tables

    # Relationship linking (foreign keys)
    selected_ids = {t.id for t in selected}
    linked = list(selected)

    for t in tables:
        if t.id in selected_ids:
            continue
        is_linked = False
        for sel_t in selected:
            for col in t.columns:
                if col.is_foreign_key and col.foreign_table_id == sel_t.id:
                    is_linked = True
                    break
            for col in sel_t.columns:
                if col.is_foreign_key and col.foreign_table_id == t.id:
                    is_linked = True
                    break
            if is_linked:
                break

        if is_linked:
            tbl_score = next((score for tbl, score in scored_tables if tbl.id == t.id), 0)
            if tbl_score >= 2:
                linked.append(t)

    return linked[:8]


def _build_schema_context_with_metadata(
    db: Session,
    datasource_id: str,
    question: str | None = None,
    optimize_rag: bool = False,
) -> tuple[str, dict[str, object]]:
    linker = SchemaLinker(db)
    if optimize_rag and question:
        linking_result = linker.link(datasource_id=datasource_id, question=question)
    else:
        linking_result = linker.full_context(datasource_id=datasource_id, question=question)

    schema_context = SchemaContextBuilder(db).build(linking_result)
    return schema_context, linking_result.response_metadata(schema_context)


def generate_schema_context(db: Session, datasource_id: str, question: str | None = None, optimize_rag: bool = False) -> str:
    """Builds a dense textual context containing table structures, comments, and relationships for LLM consumption"""
    schema_context, _metadata = _build_schema_context_with_metadata(db, datasource_id, question, optimize_rag)
    return schema_context


PROMPT_VERSION = "v1.2"

LEGACY_SYSTEM_PROMPT = (
    "You are an expert MySQL developer and data analyst.\n"
    "Your task is to generate a valid, high-performance SELECT statement to answer the user's question "
    "based on the provided schema definitions.\n\n"
    "Guidelines:\n"
    "1. Answer ONLY with the raw SQL code block. Do NOT write any introduction or explanation.\n"
    "2. Only write SELECT queries. DDL or DML statements (like INSERT, UPDATE, DROP, ALTER) are STRICTLY forbidden.\n"
    "3. Use correct table joining paths and reference fields exactly as they are defined.\n"
    "4. Always append a LIMIT clause (default to LIMIT 100) to keep results safe.\n"
    "5. Output must use standard MySQL syntax dialect.\n"
    "6. Use ONLY tables and columns present in the provided schema context; do not invent table or column names.\n"
    "7. Do NOT use BigQuery-specific functions or types such as ARRAY(), STRUCT(), UNNEST(), or ARRAY_AGG() in the SQL.\n"
    "8. For negative/anti-join intents (e.g., 'do not have', 'without', 'students who do not have X'):\n"
    "   a. ALWAYS use NOT EXISTS with a correlated subquery. NEVER use NOT IN (it fails on NULL values).\n"
    "   b. The outer FROM must reference ONLY the subject table (e.g. FROM student AS s).\n"
    "   c. Do NOT JOIN the subject table to other tables in the outer query.\n"
    "   d. The correlated subquery must join the junction table to the lookup table inside NOT EXISTS.\n"
    "   e. NEVER add DISTINCT to anti-join queries — it silently drops duplicate rows.\n"
    "   f. Template: SELECT cols FROM subject AS s WHERE NOT EXISTS (SELECT 1 FROM junction AS j JOIN lookup AS l ON j.fk = l.pk WHERE j.subject_fk = s.pk AND l.filter_col = 'value')\n"
    "9. For 'both A and B' style constraints, prefer GROUP BY ... HAVING COUNT(DISTINCT ...) = N or an equivalent self-join; avoid ad-hoc client-side filtering.\n"
    "10. Return ONLY the SQL statement; do not include explanations, examples, or surrounding markdown other than an optional sql code block."
)

SYSTEM_PROMPT = (
    "You are an expert MySQL developer and data analyst.\n"
    "Generate one valid MySQL SELECT statement from the provided schema definitions.\n"
    "If SQL_CONTRACT JSON is present in the user message, satisfy that contract.\n\n"
    "Rules:\n"
    "1. Return SQL only; no explanation.\n"
    "2. Use only tables and columns from the schema context.\n"
    "3. CRITICAL — Projection precision:\n"
    "   a. If the question asks for specific columns (e.g. 'name', 'id', 'first name'), SELECT ONLY those columns.\n"
    "   b. NEVER use SELECT * — always list explicit column names.\n"
    "   c. NEVER add COUNT(*) or aggregate functions unless the question explicitly asks for a count/aggregate.\n"
    "   d. NEVER add extra entity columns the user did not request.\n"
    "   e. If the question asks for 'how many' or 'number of', SELECT COUNT(*) [alias], nothing else.\n"
    "4. Use WHERE for scalar filters (e.g. age > 20, weight > 10).\n"
    "5. Use GROUP BY + HAVING COUNT(...) for thresholds over related rows (e.g. 'at least N flights').\n"
    "6. Use NOT EXISTS for absence of related rows (e.g. 'students without pets').\n"
    "7. Use EXISTS-pair or GROUP BY/HAVING for shared/both/intersection semantics.\n"
    "8. Do not use BigQuery-specific ARRAY(), STRUCT(), UNNEST(), or ARRAY_AGG().\n"
    "9. Append a safe LIMIT unless the query already has a bounded LIMIT."
)

SCHEMA_DIRECT_PROMPT_VERSION = "schema_direct_v1"


def _dialect_label(dialect: str) -> str:
    normalized = str(dialect or "mysql").lower()
    if normalized in {"postgres", "postgresql"}:
        return "PostgreSQL"
    if normalized == "sqlite":
        return "SQLite"
    if normalized == "mysql":
        return "MySQL"
    return dialect.strip() or "SQL"


def build_schema_direct_prompt(
    *,
    question: str,
    schema_context: str,
    dialect: str,
) -> tuple[str, str]:
    dialect_name = _dialect_label(dialect)
    system_prompt = (
        "You are a Text-to-SQL generator.\n"
        f"Generate one valid {dialect_name} SELECT statement using only the provided schema.\n"
        "Rules:\n"
        "- Return SQL only. No markdown, no explanation.\n"
        "- Use only tables and columns in schema context.\n"
        "- Preserve the user question semantics.\n"
        "- If the question asks \"how many\", \"number of\", or \"count\", use COUNT(*).\n"
        "- If the question asks \"average\", \"avg\", or \"mean\", use AVG(column).\n"
        "- If the question asks \"sum\" or \"total\", use SUM(column).\n"
        "- Do not add LIMIT to aggregate-only queries.\n"
        "- Add LIMIT only for list/detail/sample queries.\n"
        "- Do not invent tables or columns.\n"
        "- Do not use SELECT *."
    )
    user_prompt = (
        "Schema context:\n"
        f"{schema_context}\n\n"
        "User question:\n"
        f"{question}\n\n"
        "SQL:"
    )
    return system_prompt, user_prompt


def _extract_sql_from_llm_response(response_text: str) -> str:
    sql_match = re.search(r"```sql\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        generated_query = sql_match.group(1).strip()
    else:
        generated_query = re.sub(r"^```\w*\s*|\s*```$", "", response_text).strip()
    return generated_query.strip().rstrip(";")


def prepare_chat_payload(
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int = 800,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_lower = model_name.lower()
    is_openai_reasoning = any(term in model_lower for term in ("o1", "o3"))
    is_other_reasoning = any(term in model_lower for term in ("r1", "reasoner", "reasoning", "qwq"))
    is_reasoning = is_openai_reasoning or is_other_reasoning

    payload: dict[str, Any] = {
        "model": model_name,
    }
    if is_reasoning:
        new_messages = []
        system_content = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content.append(msg.get("content", ""))
            else:
                new_messages.append(dict(msg))
        if system_content:
            first_user_idx = next((i for i, m in enumerate(new_messages) if m.get("role") == "user"), None)
            if first_user_idx is not None:
                new_messages[first_user_idx]["content"] = "\n".join(system_content) + "\n\n" + new_messages[first_user_idx]["content"]
            else:
                new_messages.insert(0, {"role": "user", "content": "\n".join(system_content)})
        payload["messages"] = new_messages

        if is_openai_reasoning:
            payload["max_completion_tokens"] = 4000
        else:
            payload["max_tokens"] = 4000
            payload["temperature"] = temperature
    else:
        payload["messages"] = messages
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
    if response_format:
        payload["response_format"] = response_format
    return payload


def generate_sql_from_schema_context(
    *,
    question: str,
    schema_context: str,
    dialect: str,
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate SQL from an already-linked schema context.

    This is the default AgentKernel Text-to-SQL path. It intentionally does
    not query schema metadata, call SchemaLinker/QueryPlanBuilder, or use the
    deterministic renderer.
    """
    start_time = time.time()
    llm_config = llm_config or {}
    api_key = str(llm_config.get("api_key") or "").strip()
    api_base = str(llm_config.get("api_base") or "https://api.openai.com/v1").strip()
    model_name = str(llm_config.get("model") or llm_config.get("model_name") or "gpt-4o-mini").strip()
    dialect_name = _dialect_label(dialect)
    metadata = {
        "generation_source": "schema_direct_llm",
        "dialect": dialect,
        "used_query_plan": False,
        "used_query_plan_as_prompt": False,
        "used_renderer": False,
        "used_guardrail_in_generate": False,
        "used_semantic_retry": False,
    }

    if not api_key:
        return {
            "sql": None,
            "model": model_name,
            "mode": "schema_direct",
            "latencyMs": int((time.time() - start_time) * 1000),
            "schemaValidationWarnings": [],
            "metadata": metadata,
            "error": "LLM API key required for Text-to-SQL generation",
        }

    system_prompt, user_prompt = build_schema_direct_prompt(
        question=question,
        schema_context=schema_context,
        dialect=dialect_name,
    )
    payload = prepare_chat_payload(
        model_name=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=800,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=15.0,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        if response.status_code != 200:
            raise AIServiceError(f"LLM API returned an error (HTTP {response.status_code}): {response.text}")
        data = response.json()
        response_text = data["choices"][0]["message"]["content"].strip()
        return {
            "sql": _extract_sql_from_llm_response(response_text),
            "model": model_name,
            "mode": "schema_direct",
            "latencyMs": latency_ms,
            "schemaValidationWarnings": [],
            "metadata": metadata,
        }
    except Exception as exc:
        raise AIServiceError(f"LLM 接口调用失败: {str(exc)}")

USER_PROMPT_TEMPLATE = (
    "Available Database Tables Schema:\n"
    "```sql\n"
    "{schema_context}\n"
    "```\n\n"
    "User Question: \"{question}\"\n\n"
    "Generate SQL:"
)

PROMPT_TEMPLATE_HASH = hashlib.sha256((SYSTEM_PROMPT + USER_PROMPT_TEMPLATE).encode("utf-8")).hexdigest()


def validate_sql_schema(generated_sql: str, db: Session, datasource_id: str) -> list[str]:
    """
    Parses the generated SQL and checks for hallucinated tables and columns
    against the local schema cache in metastore.
    Returns a list of warnings if hallucinations are found.
    """
    warnings = []
    try:
        tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()
        if not tables:
            return []
        
        valid_schema = {t.table_name.lower(): {c.column_name.lower() for c in t.columns} for t in tables}
        
        parsed = sqlglot.parse_one(generated_sql, read="mysql")
        
        # 1. Extract all tables from the query
        query_tables = []
        for table_node in parsed.find_all(exp.Table):
            t_name = table_node.name.lower()
            query_tables.append(t_name)
            if t_name not in valid_schema:
                warnings.append(f"生成 SQL 包含不存在的表: `{table_node.name}`")
                
        # 2. Check column validity
        for col_node in parsed.find_all(exp.Column):
            col_name = col_node.name.lower()
            if col_name == "*" or not col_name:
                continue
                
            col_table_ref = col_node.text("table").lower()
            
            # Resolve alias or table name
            target_table = None
            if col_table_ref:
                for t_node in parsed.find_all(exp.Table):
                    alias = t_node.alias.lower() if t_node.alias else ""
                    if alias == col_table_ref or t_node.name.lower() == col_table_ref:
                        target_table = t_node.name.lower()
                        break
            
            if target_table:
                if target_table in valid_schema:
                    if col_name not in valid_schema[target_table]:
                        warnings.append(f"生成 SQL 包含表 `{target_table}` 中不存在的字段: `{col_node.name}`")
            else:
                queried_valid_tables = [t for t in query_tables if t in valid_schema]
                if queried_valid_tables:
                    exists_in_any = any(col_name in valid_schema[t] for t in queried_valid_tables)
                    if not exists_in_any:
                        tbl_list = ", ".join(f"`{t}`" for t in queried_valid_tables)
                        warnings.append(f"生成 SQL 中的字段 `{col_node.name}` 不存在于查询的表 {tbl_list} 中")
    except Exception as e:
        print(f"Schema validation error: {e}")
        
    return warnings


def generate_sql(
    db: Session, datasource_id: str, question: str, llm_config: dict[str, Any] | None = None, optimize_rag: bool = False
) -> dict[str, Any]:
    """
    LEGACY compatibility only.

    AgentKernel's default Text-to-SQL path must use
    generate_sql_from_schema_context() after schema.build_context has already
    selected and rendered the local schema context.
    """
    start_time = time.time()
    
    # 1. Read parameters
    llm_config = llm_config or {}
    api_key = llm_config.get("api_key", "").strip()
    api_base = llm_config.get("api_base", "https://api.openai.com/v1").strip()
    model_name = llm_config.get("model", "gpt-4o-mini").strip()
    
    schema_context, schema_metadata = _build_schema_context_with_metadata(db, datasource_id, question, optimize_rag)
    selected_tables_raw = schema_metadata.get("selectedTables", [])
    selected_tables = selected_tables_raw if isinstance(selected_tables_raw, list) else []
    query_plan = QueryPlanBuilder(db).build(
        datasource_id=datasource_id,
        question=question,
        schema_context=schema_context,
        llm_config=llm_config,
        selected_tables=[str(table) for table in selected_tables],
    )
    # Ensure standard prompt hash is saved
    prompt_raw = f"Context:\n{schema_context}\n\nQuestion: {question}"
    prompt_hash = hashlib.sha256(prompt_raw.encode("utf-8")).hexdigest()
    
    # 2. Require LLM API key for Text-to-SQL generation
    if not api_key:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "sql": None,
            "model": "databox",
            "mode": "fallback_unavailable",
            "latencyMs": latency_ms,
            "schemaValidationWarnings": [],
            "queryPlan": query_plan.to_dict(),
            **schema_metadata,
            "metadata": {
                "generation_source": "legacy_generate_sql",
                "fallback_reason": "no_llm_api_key",
                "blocked_reason": "no_llm_api_key",
            },
            "error": "LLM API key required for Text-to-SQL generation",
        }

    # 3. Connect to Online LLM via httpx
    # Using our hardened prompt template structures
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    user_prompt = USER_PROMPT_TEMPLATE.format(schema_context=schema_context, question=question)
    
    payload = prepare_chat_payload(
        model_name=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=800,
    )
    
    try:
        response = httpx.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=15.0
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code != 200:
            raise AIServiceError(f"LLM API returned an error (HTTP {response.status_code}): {response.text}")
            
        data = response.json()
        response_text = data["choices"][0]["message"]["content"].strip()
        
        # Extract SQL from markdown code fences if present
        sql_match = re.search(r"```sql\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            generated_query = sql_match.group(1).strip()
        else:
            # Fallback to stripping standard block characters
            generated_query = re.sub(r"^```\w*\s*|\s*```$", "", response_text).strip()
            
        # Standard cleaning
        generated_query = generated_query.replace(";", "").strip()
        
        trust_gate = TrustGate(db, validate_sql_schema).evaluate(datasource_id, generated_query)
        guard_res = trust_gate["guardrail"]
        schema_warnings = trust_gate["schemaWarnings"]
        
        # Log to db with versioning & audit parameters
        log_entry = LLMLog(
            request_type="text_to_sql",
            data_source_id=datasource_id,
            prompt_hash=prompt_hash,
            model_name=model_name,
            latency_ms=latency_ms,
            status="success",
            prompt_version=PROMPT_VERSION,
            prompt_template_hash=PROMPT_TEMPLATE_HASH,
            model_temperature=0.1,
            max_tokens=800,
            schema_validation_warnings="; ".join(schema_warnings) if schema_warnings else None
        )
        _persist_llm_log(db, log_entry)
        
        return {
            "sql": generated_query,
            "model": model_name,
            "latencyMs": latency_ms,
            "guardrail": guard_res,
            "trustGate": trust_gate,
            "mode": "online",
            "schemaValidationWarnings": schema_warnings,
            "queryPlan": query_plan.to_dict(),
            **schema_metadata,
        }
        
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        # Log failure
        log_entry = LLMLog(
            request_type="text_to_sql",
            data_source_id=datasource_id,
            prompt_hash=prompt_hash,
            model_name=model_name,
            latency_ms=latency_ms,
            status="failed",
            error_message=str(e),
            prompt_version=PROMPT_VERSION,
            prompt_template_hash=PROMPT_TEMPLATE_HASH,
            model_temperature=0.1,
            max_tokens=800
        )
        _persist_llm_log(db, log_entry)
        raise AIServiceError(f"LLM 接口调用失败: {str(e)}")


AI_TABLE_DESIGN_SYSTEM_PROMPT = (
    "You are an expert database architect.\n"
    "Your task is to design a high-performance MySQL table schema based on the user's natural language request.\n"
    "You must output ONLY a valid JSON object matching the following structure. Do NOT include any markdown code blocks, explanation or additional characters.\n"
    "JSON Structure:\n"
    "{\n"
    "  \"table_name\": \"string (snake_case database table name)\",\n"
    "  \"table_comment\": \"string (brief Chinese explanation of what the table stores)\",\n"
    "  \"columns\": [\n"
    "    {\n"
    "      \"name\": \"string (column name in snake_case)\",\n"
    "      \"type\": \"string (standard MySQL column type, e.g., BIGINT, VARCHAR(255), INT, TIMESTAMP, DECIMAL(10,2))\",\n"
    "      \"nullable\": true/false,\n"
    "      \"primary_key\": true/false,\n"
    "      \"auto_increment\": true/false,\n"
    "      \"default_value\": \"string or null\",\n"
    "      \"comment\": \"string (brief Chinese description of column content)\"\n"
    "    }\n"
    "  ],\n"
    "  \"indexes\": [\n"
    "    {\n"
    "      \"name\": \"string (snake_case index name, e.g., idx_table_col)\",\n"
    "      \"columns\": [\"string (column name)\"],\n"
    "      \"unique\": true/false\n"
    "    }\n"
    "  ]\n"
    "}\n"
)


def generate_table_design_ai(
    question: str, llm_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Generates a premium MySQL table schema (columns and indexes) using AI or dynamic heuristics fallback.
    """
    llm_config = llm_config or {}
    api_key = llm_config.get("api_key", "").strip()
    api_base = llm_config.get("api_base", "https://api.openai.com/v1").strip()
    model_name = llm_config.get("model", "gpt-4o-mini").strip()

    if not api_key:
        raise AIServiceError("LLM API key required for AI table design generation")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = prepare_chat_payload(
        model_name=model_name,
        messages=[
            {"role": "system", "content": AI_TABLE_DESIGN_SYSTEM_PROMPT},
            {"role": "user", "content": f"User Request: \"{question}\"\nGenerate Table Design JSON:"}
        ],
        temperature=0.2,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    try:
        response = httpx.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=20.0
        )
        if response.status_code != 200:
            raise AIServiceError(f"LLM API returned an error (HTTP {response.status_code}): {response.text}")
            
        data = response.json()
        response_text = data["choices"][0]["message"]["content"].strip()
        
        import json
        design_json: dict[str, Any] = json.loads(response_text)
        return design_json
    except Exception as e:
        raise AIServiceError(f"AI table design generation failed: {e}")


AI_SCHEMA_ALTERATION_SYSTEM_PROMPT = (
    "You are a database architecture expert.\n"
    "You will receive the current MySQL database schema and an instruction describing how to alter or modify the schema.\n"
    "Your task is to generate valid MySQL DDL statements (such as ALTER TABLE, CREATE TABLE, etc.) to apply the specified changes.\n\n"
    "Guidelines:\n"
    "1. Respond ONLY with the raw SQL code block. Do NOT write any introduction or explanation.\n"
    "2. Make sure the generated SQL statements are completely syntactically correct in standard MySQL dialect.\n"
    "3. Do not drop existing tables or columns unless explicitly asked by the instruction.\n"
    "4. Ensure that the table and column names referenced match the current database schema accurately."
)

def generate_schema_alteration_ai(
    db: Session,
    datasource_id: str,
    instruction: str,
    llm_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Generates MySQL DDL statements to alter schema based on natural language annotations.
    """
    llm_config = llm_config or {}
    api_key = llm_config.get("api_key", "").strip()
    api_base = llm_config.get("api_base", "https://api.openai.com/v1").strip()
    model_name = llm_config.get("model", "gpt-4o-mini").strip()

    if not api_key:
        raise AIServiceError("LLM API key required for AI schema alteration generation")

    schema_context = generate_schema_context(db, datasource_id, instruction, optimize_rag=False)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    user_prompt = (
        f"Current Database Schema:\n```sql\n{schema_context}\n```\n\n"
        f"Instruction: \"{instruction}\"\n\n"
        f"Generate DDL Diffs:"
    )

    payload = prepare_chat_payload(
        model_name=model_name,
        messages=[
            {"role": "system", "content": AI_SCHEMA_ALTERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=1000,
    )

    try:
        response = httpx.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=20.0
        )
        if response.status_code != 200:
            raise AIServiceError(f"LLM API returned an error (HTTP {response.status_code}): {response.text}")
            
        data = response.json()
        response_text = data["choices"][0]["message"]["content"].strip()

        # Extract SQL from markdown code fences
        sql_match = re.search(r"```sql\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            generated_ddl = sql_match.group(1).strip()
        else:
            generated_ddl = re.sub(r"^```\w*\s*|\s*```$", "", response_text).strip()

        return {"ddl": generated_ddl, "model": model_name, "mode": "online"}
    except Exception as e:
        raise AIServiceError(f"AI schema alteration generation failed: {e}")

