from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

import httpx
from sqlalchemy.orm import Session, selectinload

from engine.models import SchemaColumn, SchemaTable, SemanticDimension, SemanticMetric


def _parse_source_columns(source_columns_json: str | None) -> list[str]:
    if not source_columns_json:
        return []
    try:
        parsed = json.loads(source_columns_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _extract_table_from_ref(ref: str) -> str:
    parts = ref.split(".", 1)
    return parts[0] if len(parts) == 2 else ""


PlanBuildMode = Literal["auto", "offline", "online"]


@dataclass
class QueryMetric:
    name: str
    expression: str
    source_column: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "expression": self.expression,
            "source_column": self.source_column,
        }


@dataclass
class QueryDimension:
    name: str
    column: str
    transform: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "column": self.column,
            "transform": self.transform,
        }


@dataclass
class QueryFilter:
    column: str
    operator: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "column": self.column,
            "operator": self.operator,
            "value": self.value,
        }


@dataclass
class QueryJoin:
    left_table: str
    right_table: str
    condition: str

    def to_dict(self) -> dict[str, str]:
        return {
            "left_table": self.left_table,
            "right_table": self.right_table,
            "condition": self.condition,
        }


@dataclass
class QueryPlan:
    intent: str
    tables: list[str] = field(default_factory=list)
    metrics: list[QueryMetric] = field(default_factory=list)
    dimensions: list[QueryDimension] = field(default_factory=list)
    filters: list[QueryFilter] = field(default_factory=list)
    joins: list[QueryJoin] = field(default_factory=list)
    order_by: str | None = None
    limit: int = 100
    warnings: list[str] = field(default_factory=list)
    mode: str = "offline"

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "tables": self.tables,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "filters": [item.to_dict() for item in self.filters],
            "joins": [join.to_dict() for join in self.joins],
            "order_by": self.order_by,
            "limit": self.limit,
            "warnings": self.warnings,
            "mode": self.mode,
        }


QUERY_PLAN_SYSTEM_PROMPT = (
    "You are a query planning assistant for a local Text-to-SQL system.\n"
    "Return ONLY a JSON object. Do not include markdown, explanations, or hidden reasoning.\n"
    "Use only tables and columns present in the schema context.\n"
    "The JSON object must contain: intent, tables, metrics, dimensions, filters, joins, order_by, limit.\n"
    "metrics items: name, expression, source_column.\n"
    "dimensions items: name, column, transform.\n"
    "filters items: column, operator, value.\n"
    "joins items: left_table, right_table, condition."
)

QUERY_PLAN_USER_TEMPLATE = (
    "Schema context:\n"
    "```sql\n"
    "{schema_context}\n"
    "```\n"
    "{semantic_context}\n"
    "User question: \"{question}\"\n\n"
    "Generate the structured query plan JSON:"
)


class QueryPlanBuilder:
    """Build and validate an explainable query plan before SQL generation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(
        self,
        datasource_id: str,
        question: str,
        schema_context: str = "",
        llm_config: dict[str, Any] | None = None,
        selected_tables: Sequence[str] | None = None,
        mode: PlanBuildMode = "auto",
    ) -> QueryPlan:
        config = llm_config or {}
        api_key = str(config.get("api_key", "") or "").strip()
        actual_mode: Literal["offline", "online"] = "online" if mode == "auto" and api_key else "offline"
        if mode in ("offline", "online"):
            actual_mode = mode  # type: ignore[assignment]

        if actual_mode == "online" and api_key:
            try:
                plan = self._build_online(
                    question=question,
                    schema_context=schema_context,
                    llm_config=config,
                    datasource_id=datasource_id,
                )
                plan.mode = "online"
                return self.validate(datasource_id, plan)
            except Exception as exc:
                plan = self._build_offline(datasource_id, question, selected_tables)
                plan.mode = "offline_fallback"
                plan.warnings.append(f"online_query_plan_failed:{type(exc).__name__}")
                return self.validate(datasource_id, plan)

        plan = self._build_offline(datasource_id, question, selected_tables)
        plan.mode = "offline"
        return self.validate(datasource_id, plan)

    def validate(self, datasource_id: str, plan: QueryPlan) -> QueryPlan:
        schema = self._load_schema(datasource_id)
        warnings = list(plan.warnings)

        for table_name in plan.tables:
            if table_name.lower() not in schema:
                warnings.append(f"QueryPlan references missing table `{table_name}`")

        for metric in plan.metrics:
            warnings.extend(self._validate_column_ref(schema, metric.source_column, "metric.source_column", plan.tables))
            warnings.extend(self._validate_expression_refs(schema, metric.expression, "metric.expression"))

        for dimension in plan.dimensions:
            warnings.extend(self._validate_column_ref(schema, dimension.column, "dimension.column", plan.tables))

        for item in plan.filters:
            warnings.extend(self._validate_column_ref(schema, item.column, "filter.column", plan.tables))

        for join in plan.joins:
            if join.left_table.lower() not in schema:
                warnings.append(f"QueryPlan references missing join table `{join.left_table}`")
            if join.right_table.lower() not in schema:
                warnings.append(f"QueryPlan references missing join table `{join.right_table}`")
            warnings.extend(self._validate_expression_refs(schema, join.condition, "join.condition"))

        if plan.order_by:
            warnings.extend(self._validate_expression_refs(schema, plan.order_by, "order_by"))

        plan.warnings = _dedupe(warnings)
        return plan

    def _build_semantic_context_text(self, datasource_id: str) -> str:
        metrics, dimensions = self._load_semantic_definitions(datasource_id)
        parts: list[str] = []

        if metrics:
            parts.append("Predefined metrics:")
            for m in metrics:
                parts.append(f"  - {m.name}: {m.expression} (source: {m.source_column})")

        if dimensions:
            parts.append("Predefined dimensions:")
            for d in dimensions:
                transform_str = f" [{d.transform}]" if d.transform else ""
                parts.append(f"  - {d.name}: {d.column}{transform_str}")

        if not parts:
            return ""

        return "\n".join(parts) + "\n"

    def _build_online(
        self,
        question: str,
        schema_context: str,
        llm_config: dict[str, Any],
        datasource_id: str = "",
    ) -> QueryPlan:
        api_key = str(llm_config.get("api_key", "") or "").strip()
        api_base = str(llm_config.get("api_base", "https://api.openai.com/v1") or "").strip()
        model_name = str(llm_config.get("model", "gpt-4o-mini") or "").strip()
        if not api_key:
            raise ValueError("missing api_key")

        semantic_context = self._build_semantic_context_text(datasource_id)

        response = httpx.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": QUERY_PLAN_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": QUERY_PLAN_USER_TEMPLATE.format(
                            schema_context=schema_context,
                            semantic_context=f"\n{semantic_context}" if semantic_context else "",
                            question=question,
                        ),
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            },
            timeout=12.0,
        )
        if response.status_code != 200:
            raise ValueError(f"plan LLM HTTP {response.status_code}")

        content = str(response.json()["choices"][0]["message"]["content"]).strip()
        return self._plan_from_dict(_parse_json_object(content), mode="online")

    def _build_offline(
        self,
        datasource_id: str,
        question: str,
        selected_tables: Sequence[str] | None,
    ) -> QueryPlan:
        q = question.lower()

        # 1. Check semantic definitions from DB
        metrics, dimensions = self._load_semantic_definitions(datasource_id)
        matched_metrics = self._match_metrics(q, metrics)
        matched_dimensions = self._match_dimensions(q, dimensions)

        if matched_metrics or matched_dimensions:
            tables_set: set[str] = set()
            for m in matched_metrics:
                source_cols = _parse_source_columns(m.source_columns_json)  # type: ignore[arg-type]
                source_col = source_cols[0] if source_cols else m.expression
                table = _extract_table_from_ref(str(source_col)) if source_col else None
                if table:
                    tables_set.add(table)
            for d in matched_dimensions:
                table = _extract_table_from_ref(d.column_ref)  # type: ignore[arg-type]
                if table:
                    tables_set.add(table)

            if selected_tables:
                available = {table.lower() for table in selected_tables}
                tables_set = {table for table in tables_set if table.lower() in available}

            tables = list(tables_set) if tables_set else self._fallback_tables(datasource_id, selected_tables)
            source_cols = _parse_source_columns(matched_metrics[0].source_columns_json) if matched_metrics else []  # type: ignore[arg-type]
            return QueryPlan(
                intent="answer_question_with_semantic_definitions",
                tables=tables,
                metrics=[
                    QueryMetric(
                        name=m.name,  # type: ignore[arg-type]
                        expression=m.expression,  # type: ignore[arg-type]
                        source_column=_parse_source_columns(m.source_columns_json)[0] if _parse_source_columns(m.source_columns_json) else "",  # type: ignore[arg-type]
                    )
                    for m in matched_metrics
                ],
                dimensions=[
                    QueryDimension(
                        name=d.name,  # type: ignore[arg-type]
                        column=d.column_ref,  # type: ignore[arg-type]
                        transform=d.transform if d.transform else None,  # type: ignore[arg-type]
                    )
                    for d in matched_dimensions
                ],
                filters=[],
                joins=self._infer_joins(datasource_id, tables),
                order_by=None,
                limit=100,
            )

        # 2. Existing offline heuristics (unchanged)
        if self._has_sales_volume_intent(q):
            tables = self._available_tables(datasource_id, ["order_items", "products"], selected_tables)
            return QueryPlan(
                intent="rank_products_by_sales_volume",
                tables=tables,
                metrics=[
                    QueryMetric(
                        name="total_sold",
                        expression="SUM(order_items.quantity)",
                        source_column="order_items.quantity",
                    )
                ],
                dimensions=[QueryDimension(name="product_name", column="products.name", transform=None)],
                joins=self._infer_joins(datasource_id, tables),
                order_by="total_sold DESC",
                limit=10,
            )

        if self._has_order_count_intent(q):
            tables = self._available_tables(datasource_id, ["orders"], selected_tables)
            out_dimensions: list[QueryDimension] = []
            if _contains_any(q, ("每天", "每日", "按天", "daily", "per day")):
                out_dimensions.append(QueryDimension(name="order_date", column="orders.created_at", transform="DATE"))
            return QueryPlan(
                intent="aggregate_order_count",
                tables=tables,
                metrics=[
                    QueryMetric(
                        name="order_count",
                        expression="COUNT(*)",
                        source_column="orders.id",
                    )
                ],
                dimensions=out_dimensions,
                filters=self._order_status_filters(q),
                joins=[],
                order_by="order_date DESC" if out_dimensions else None,
                limit=100,
            )

        if self._has_amount_intent(q):
            tables = self._available_tables(datasource_id, ["orders"], selected_tables)
            out_dimensions = []
            if _contains_any(q, ("每天", "每日", "按天", "daily", "per day")):
                out_dimensions.append(QueryDimension(name="order_date", column="orders.created_at", transform="DATE"))
            return QueryPlan(
                intent="aggregate_order_amount",
                tables=tables,
                metrics=[
                    QueryMetric(
                        name="total_amount",
                        expression="SUM(orders.total_amount)",
                        source_column="orders.total_amount",
                    )
                ],
                dimensions=out_dimensions,
                filters=self._order_status_filters(q),
                joins=[],
                order_by="order_date DESC" if out_dimensions else None,
                limit=100,
            )

        if _contains_any(q, ("用户", "客户", "user", "customer")) and _contains_any(q, ("数量", "多少", "count", "统计")):
            tables = self._available_tables(datasource_id, ["users"], selected_tables)
            return QueryPlan(
                intent="aggregate_user_count",
                tables=tables,
                metrics=[QueryMetric(name="user_count", expression="COUNT(*)", source_column="users.id")],
                dimensions=[],
                filters=[],
                joins=[],
                order_by=None,
                limit=100,
            )

        tables = self._fallback_tables(datasource_id, selected_tables)
        out_metrics: list[QueryMetric] = []
        if _contains_any(q, ("数量", "多少", "count", "统计")) and tables:
            out_metrics.append(QueryMetric(name="row_count", expression="COUNT(*)", source_column=f"{tables[0]}.id"))

        # Detect ordering intent in default / answer_question plans
        out_order_by = _detect_ordering_intent(q, tables, self.db, datasource_id)

        return QueryPlan(
            intent="answer_question",
            tables=tables,
            metrics=out_metrics,
            dimensions=[],
            filters=[],
            joins=self._infer_joins(datasource_id, tables),
            order_by=out_order_by,
            limit=100,
        )

    def _load_semantic_definitions(
        self, datasource_id: str
    ) -> tuple[list[SemanticMetric], list[SemanticDimension]]:
        metrics = (
            self.db.query(SemanticMetric)
            .filter(SemanticMetric.data_source_id == datasource_id)
            .all()
        )
        dimensions = (
            self.db.query(SemanticDimension)
            .filter(SemanticDimension.data_source_id == datasource_id)
            .all()
        )
        return metrics, dimensions

    def _match_metrics(self, q_lower: str, metrics: list[SemanticMetric]) -> list[SemanticMetric]:
        matched: list[SemanticMetric] = []
        for m in metrics:
            if m.name.lower() in q_lower:
                matched.append(m)
        return matched

    def _match_dimensions(self, q_lower: str, dimensions: list[SemanticDimension]) -> list[SemanticDimension]:
        matched: list[SemanticDimension] = []
        for d in dimensions:
            if d.name.lower() in q_lower:
                matched.append(d)
        return matched

    def _has_sales_volume_intent(self, q: str) -> bool:
        return _contains_any(q, ("销量", "销售量", "total_sold", "sold")) and _contains_any(
            q,
            ("商品", "产品", "product", "最高", "top", "排行", "排名"),
        )

    def _has_order_count_intent(self, q: str) -> bool:
        return _contains_any(q, ("订单量", "订单数", "订单数量", "order count", "orders count"))

    def _has_amount_intent(self, q: str) -> bool:
        return _contains_any(q, ("销售额", "gmv", "订单金额", "总金额", "total_amount", "revenue"))

    def _order_status_filters(self, q: str) -> list[QueryFilter]:
        if _contains_any(q, ("取消", "cancelled", "canceled")):
            return [QueryFilter(column="orders.status", operator="=", value="cancelled")]
        if _contains_any(q, ("完成", "completed")):
            return [QueryFilter(column="orders.status", operator="=", value="completed")]
        return []

    def _available_tables(
        self,
        datasource_id: str,
        preferred: Sequence[str],
        selected_tables: Sequence[str] | None,
    ) -> list[str]:
        schema = self._load_schema(datasource_id)
        preferred_existing = [table for table in preferred if table.lower() in schema]
        if preferred_existing:
            return preferred_existing
        return self._fallback_tables(datasource_id, selected_tables)

    def _fallback_tables(self, datasource_id: str, selected_tables: Sequence[str] | None) -> list[str]:
        schema = self._load_schema(datasource_id)
        if selected_tables:
            existing = [table for table in selected_tables if table.lower() in schema]
            if existing:
                return existing[:3]
        return list(schema.keys())[:1]

    def _infer_joins(self, datasource_id: str, tables: Sequence[str]) -> list[QueryJoin]:
        if len(tables) < 2:
            return []

        table_set = {table.lower() for table in tables}
        schema_tables = (
            self.db.query(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        )
        table_id_to_name = {str(table.id): str(table.table_name) for table in schema_tables}
        column_id_to_name = {
            str(column.id): str(column.column_name)
            for table in schema_tables
            for column in table.columns
        }

        joins: list[QueryJoin] = []
        for table in schema_tables:
            left_table = str(table.table_name)
            if left_table.lower() not in table_set:
                continue
            for column in table.columns:
                if not column.is_foreign_key or not column.foreign_table_id:
                    continue
                right_table = table_id_to_name.get(str(column.foreign_table_id))
                if not right_table or right_table.lower() not in table_set:
                    continue
                right_column = column_id_to_name.get(str(column.foreign_column_id or ""), "id")
                joins.append(
                    QueryJoin(
                        left_table=left_table,
                        right_table=right_table,
                        condition=f"{left_table}.{column.column_name} = {right_table}.{right_column}",
                    )
                )
        return joins

    def _load_schema(self, datasource_id: str) -> dict[str, set[str]]:
        tables = (
            self.db.query(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        )
        return {
            str(table.table_name).lower(): {str(column.column_name).lower() for column in table.columns}
            for table in tables
        }

    def _validate_column_ref(
        self,
        schema: dict[str, set[str]],
        ref: str,
        source: str,
        table_scope: Sequence[str] | None = None,
    ) -> list[str]:
        ref = (ref or "").strip()
        if not ref or ref == "*":
            return []
        parsed = _split_column_ref(ref)
        if not parsed and _is_identifier(ref):
            scope = [table.lower() for table in table_scope or [] if table.lower() in schema] or list(schema.keys())
            if any(ref.lower() in schema[table] for table in scope):
                return []
            return [f"QueryPlan {source} references missing column `{ref}`"]
        if not parsed:
            return []
        table_name, column_name = parsed
        if table_name.lower() not in schema:
            return [f"QueryPlan {source} references missing table `{table_name}`"]
        if column_name != "*" and column_name.lower() not in schema[table_name.lower()]:
            return [f"QueryPlan {source} references missing column `{table_name}.{column_name}`"]
        return []

    def _validate_expression_refs(self, schema: dict[str, set[str]], expression: str, source: str) -> list[str]:
        warnings: list[str] = []
        for table_name, column_name in _find_qualified_refs(expression):
            warnings.extend(self._validate_column_ref(schema, f"{table_name}.{column_name}", source))
        return warnings

    def _plan_from_dict(self, payload: dict[str, Any], mode: str) -> QueryPlan:
        metrics = [
            QueryMetric(
                name=str(item.get("name", "")),
                expression=str(item.get("expression", "")),
                source_column=str(item.get("source_column", "")),
            )
            for item in _list_of_dicts(payload.get("metrics"))
        ]
        dimensions = [
            QueryDimension(
                name=str(item.get("name", "")),
                column=str(item.get("column", "")),
                transform=str(item["transform"]) if item.get("transform") is not None else None,
            )
            for item in _list_of_dicts(payload.get("dimensions"))
        ]
        filters = [
            QueryFilter(
                column=str(item.get("column", "")),
                operator=str(item.get("operator", "")),
                value=str(item.get("value", "")),
            )
            for item in _list_of_dicts(payload.get("filters"))
        ]
        joins = [
            QueryJoin(
                left_table=str(item.get("left_table", "")),
                right_table=str(item.get("right_table", "")),
                condition=str(item.get("condition", "")),
            )
            for item in _list_of_dicts(payload.get("joins"))
        ]
        return QueryPlan(
            intent=str(payload.get("intent", "answer_question")),
            tables=[str(table) for table in _list_values(payload.get("tables"))],
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            joins=joins,
            order_by=str(payload["order_by"]) if payload.get("order_by") is not None else None,
            limit=_coerce_limit(payload.get("limit")),
            warnings=[str(item) for item in _list_values(payload.get("warnings"))],
            mode=mode,
        )


def _parse_json_object(content: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
    cleaned = match.group(1).strip() if match else content.strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("query plan response is not a JSON object")
    return parsed


def _list_values(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_limit(value: object) -> int:
    if value is None:
        return 100
    if isinstance(value, bool):
        return 100
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 100
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 100
    return max(1, min(limit, 1000))


def _detect_ordering_intent(
    question: str,
    tables: list[str],
    db: Session,
    datasource_id: str,
) -> str | None:
    """Detect ordering keywords in *question* and try to extract
    a column + direction for the ORDER BY clause.
    Returns a string like ``age DESC`` or None.
    """
    q = question.lower()
    ordering_keywords = (
        "ordered by", "order by", "sorted by", "sort by",
        "oldest to youngest", "youngest to oldest",
        "newest to oldest", "oldest to newest",
        "highest to lowest", "lowest to highest",
        "largest to smallest", "smallest to largest",
        "descending", "ascending",
    )
    if not any(kw in q for kw in ordering_keywords):
        return None

    # Determine direction
    desc_markers = (
        "oldest to youngest", "newest to oldest",
        "highest to lowest", "largest to smallest",
        "descending", "desc", "from the oldest",
    )
    direction = "DESC" if any(m in q for m in desc_markers) else "ASC"

    # Try to find a column name from the schema that appears in the question
    from engine.models import SchemaTable as _ST, SchemaColumn as _SC
    from sqlalchemy.orm import selectinload as _selectinload

    schema_tables = (
        db.query(_ST)
        .options(_selectinload(_ST.columns))
        .filter(_ST.data_source_id == datasource_id)
        .all()
    )
    candidate_columns: list[tuple[str, str]] = []  # (col_name, table_name)
    for st in schema_tables:
        for col in st.columns:
            col_name = str(col.column_name).lower()
            if col_name in q:
                candidate_columns.append((col_name, str(st.table_name)))

    if not candidate_columns:
        return None

    # Prefer columns mentioned near the ordering keyword
    col_name = candidate_columns[0][0]
    return f"{col_name} {direction}"


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _split_column_ref(ref: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"`?([A-Za-z_][\w]*)`?\.`?([A-Za-z_*][\w*]*)`?", ref.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _is_identifier(ref: str) -> bool:
    return re.fullmatch(r"`?[A-Za-z_][\w]*`?", ref.strip()) is not None


def _find_qualified_refs(expression: str) -> list[tuple[str, str]]:
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(r"`?([A-Za-z_][\w]*)`?\.`?([A-Za-z_*][\w*]*)`?", expression or "")
    ]


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
