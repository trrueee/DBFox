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
            actual_mode = mode

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

        schema_plan = self._build_schema_matched_offline(datasource_id, q, selected_tables)
        if schema_plan is not None:
            return schema_plan

        tables = self._fallback_tables(datasource_id, selected_tables)
        return QueryPlan(
            intent="answer_question",
            tables=tables,
            joins=self._infer_joins(datasource_id, tables),
            order_by=_detect_ordering_intent(q, tables, self.db, datasource_id),
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

    def _build_schema_matched_offline(
        self,
        datasource_id: str,
        q_lower: str,
        selected_tables: Sequence[str] | None,
    ) -> QueryPlan | None:
        if _contains_any(q_lower, ("delete", "drop", "truncate", "update", "insert", "删除", "清空", "更新", "写入")):
            return None

        schema_tables = self._load_schema_tables(datasource_id, selected_tables)
        if not schema_tables:
            return None

        question_terms = _question_terms(q_lower)
        ranked_tables = sorted(
            ((self._table_match_score(table, question_terms), table) for table in schema_tables),
            key=lambda item: item[0],
            reverse=True,
        )
        matched_tables = [table for score, table in ranked_tables if score > 0]
        if not matched_tables:
            return None

        aggregate = _contains_any(q_lower, ("数量", "多少", "count", "统计", "总数", "量", "sum", "total", "revenue", "销售额", "销量", "how many", "number of", "how much"))
        avg_intent = _contains_any(q_lower, ("average", "avg", "mean", "平均", "均值"))
        rank = _contains_any(q_lower, ("top", "highest", "最大", "最高", "排行", "排名", "most", "least", "最少", "最低"))
        daily = _contains_any(q_lower, ("每天", "每日", "按天", "daily", "per day"))
        grouping = _contains_any(q_lower, ("per", "each", "by", "每", "按", "每个", "group by", "分组"))

        metrics: list[QueryMetric] = []
        dimensions: list[QueryDimension] = []

        metric_table = matched_tables[0]
        sum_column = self._best_sum_column(matched_tables, question_terms)
        if sum_column is not None and _contains_any(q_lower, ("sum", "total", "revenue", "销售额", "销量", "销售量", "sold", "amount", "金额", "gmv")):
            metric_table, column = sum_column
            col_name = column.column_name
            if col_name.lower().startswith("total_"):
                metric_name = col_name.lower()
            else:
                metric_name = "total_sold" if "quantity" in col_name.lower() else f"total_{col_name}"
            metrics.append(
                QueryMetric(
                    name=metric_name,
                    expression=f"SUM({metric_table.table_name}.{column.column_name})",
                    source_column=f"{metric_table.table_name}.{column.column_name}",
                )
            )
        elif avg_intent:
            best_col = self._best_numeric_column(matched_tables, metric_table)
            if best_col is not None:
                col_name = best_col.column_name
                tbl_name = metric_table.table_name
                metrics.append(
                    QueryMetric(
                        name=f"avg_{col_name}",
                        expression=f"AVG({tbl_name}.{col_name})",
                        source_column=f"{tbl_name}.{col_name}",
                    )
                )
            else:
                metrics.append(
                    QueryMetric(
                        name=f"{_singular(str(metric_table.table_name))}_count",
                        expression="COUNT(*)",
                        source_column=f"{metric_table.table_name}.{self._primary_or_first_column(metric_table)}",
                    )
                )
        elif aggregate:
            source_column = self._primary_or_first_column(metric_table)
            metrics.append(
                QueryMetric(
                    name=f"{_singular(str(metric_table.table_name))}_count",
                    expression="COUNT(*)",
                    source_column=f"{metric_table.table_name}.{source_column}",
                )
            )

        # Only add dimensions for grouping/per/each/by questions.
        # Aggregate-only questions (e.g. "How many students?") should NOT get dimensions.
        needs_dimensions = grouping or (
            not metrics and _contains_any(q_lower, ("list", "show", "列出", "显示", "name", "what", "which", "who", "find"))
        )
        if needs_dimensions:
            dimension_column = self._best_dimension_column(matched_tables, question_terms, daily=daily)
            if dimension_column is not None:
                dimension_table, column, transform = dimension_column
                dimensions.append(
                    QueryDimension(
                        name=f"{_singular(str(dimension_table.table_name))}_{column.column_name if not transform else 'date'}",
                        column=f"{dimension_table.table_name}.{column.column_name}",
                        transform=transform,
                    )
                )

        tables = _ordered_unique(
            [str(metric_table.table_name)]
            + [str(table.table_name) for table in matched_tables[:2]]
            + [_extract_table_from_ref(metric.source_column) for metric in metrics]
            + [_extract_table_from_ref(dimension.column) for dimension in dimensions]
        )
        order_by = None
        if rank and metrics:
            order_by = f"{metrics[0].name} DESC"
        elif daily and dimensions:
            order_by = f"{dimensions[0].name} DESC"

        intent = "schema_matched_aggregate" if metrics else "schema_matched_lookup"
        if order_by and metrics and any(metric.name == "total_sold" for metric in metrics):
            intent = "rank_products_by_sales_volume"

        # Aggregate-only (COUNT/AVG/SUM without dimensions): no LIMIT needed.
        # Lookup/list queries and ranked queries: keep LIMIT.
        is_aggregate_only = bool(metrics and not dimensions and not rank)

        return QueryPlan(
            intent=intent,
            tables=tables,
            metrics=metrics,
            dimensions=dimensions,
            filters=self._schema_matched_filters(q_lower, tables),
            joins=self._infer_joins(datasource_id, tables),
            order_by=order_by,
            limit=None if is_aggregate_only else (10 if rank else 100),
        )

    def _load_schema_tables(self, datasource_id: str, selected_tables: Sequence[str] | None) -> list[SchemaTable]:
        query = (
            self.db.query(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .filter(SchemaTable.data_source_id == datasource_id)
        )
        tables = query.all()
        if selected_tables:
            selected = {table.lower() for table in selected_tables}
            tables = [table for table in tables if str(table.table_name).lower() in selected]
        return tables

    def _table_match_score(self, table: SchemaTable, question_terms: set[str]) -> int:
        labels = _schema_terms(str(table.table_name), str(table.table_comment or ""))
        for column in table.columns:
            labels.update(_schema_terms(str(column.column_name), str(column.column_comment or "")))
        return len(labels & question_terms)

    def _best_numeric_column(
        self,
        tables: Sequence[SchemaTable],
        fallback_table: SchemaTable,
    ) -> SchemaColumn | None:
        """Find the most likely numeric column for AVG/statistical queries."""
        numeric_types = ("int", "decimal", "numeric", "float", "double", "real")
        # Prefer columns in the fallback_table, then scan all tables.
        ordered = [fallback_table] + [t for t in tables if t.table_name != fallback_table.table_name]
        for table in ordered:
            for column in table.columns:
                type_text = f"{column.data_type or ''} {column.column_type or ''}".lower()
                if not any(token in type_text for token in numeric_types):
                    continue
                name = str(column.column_name).lower()
                # Prefer metric-like columns: score, amount, price, value, etc.
                if any(token in name for token in ("score", "amount", "price", "value", "gmv", "revenue", "sales")):
                    return column
            # Fallback: first numeric column in this table
            for column in table.columns:
                type_text = f"{column.data_type or ''} {column.column_type or ''}".lower()
                if any(token in type_text for token in numeric_types):
                    return column
        return None

    def _best_sum_column(
        self,
        tables: Sequence[SchemaTable],
        question_terms: set[str],
    ) -> tuple[SchemaTable, SchemaColumn] | None:
        numeric_types = ("int", "decimal", "numeric", "float", "double", "real")
        candidates: list[tuple[int, SchemaTable, SchemaColumn]] = []
        for table in tables:
            for column in table.columns:
                type_text = f"{column.data_type or ''} {column.column_type or ''}".lower()
                if not any(token in type_text for token in numeric_types):
                    continue
                terms = _schema_terms(str(column.column_name), str(column.column_comment or ""))
                score = len(terms & question_terms)
                if terms & {"quantity", "amount", "total", "price", "revenue", "sold", "sales"}:
                    score += 2
                candidates.append((score, table, column))
        if not candidates:
            return None
        score, table, column = max(candidates, key=lambda item: item[0])
        return (table, column) if score > 0 else None

    def _best_dimension_column(
        self,
        tables: Sequence[SchemaTable],
        question_terms: set[str],
        *,
        daily: bool,
    ) -> tuple[SchemaTable, SchemaColumn, str | None] | None:
        if daily:
            for table in tables:
                for column in table.columns:
                    name = str(column.column_name).lower()
                    type_text = f"{column.data_type or ''} {column.column_type or ''}".lower()
                    if "date" in name or "time" in name or "date" in type_text or "time" in type_text:
                        return table, column, "DATE"

        candidates: list[tuple[int, SchemaTable, SchemaColumn]] = []
        for table in tables:
            table_terms = _schema_terms(str(table.table_name), str(table.table_comment or ""))
            for column in table.columns:
                column_name = str(column.column_name).lower()
                if column.is_primary_key or column.is_foreign_key or column_name.endswith("_id"):
                    continue
                terms = _schema_terms(str(column.column_name), str(column.column_comment or ""))
                score = len(terms & question_terms)
                if terms & {"name", "title", "country", "category", "status"}:
                    score += 1
                if (table_terms & question_terms) and (terms & {"name", "title"}):
                    score += 3
                candidates.append((score, table, column))
        if not candidates:
            return None
        score, table, column = max(candidates, key=lambda item: item[0])
        return (table, column, None) if score > 0 else None

    def _primary_or_first_column(self, table: SchemaTable) -> str:
        for column in table.columns:
            if column.is_primary_key:
                return str(column.column_name)
        return str(table.columns[0].column_name) if table.columns else "id"

    def _schema_matched_filters(self, q_lower: str, tables: Sequence[str]) -> list[QueryFilter]:
        if "orders" in {table.lower() for table in tables}:
            return self._order_status_filters(q_lower)
        return []

    def _order_status_filters(self, q: str) -> list[QueryFilter]:
        if _contains_any(q, ("取消", "cancelled", "canceled")):
            return [QueryFilter(column="orders.status", operator="=", value="cancelled")]
        if _contains_any(q, ("完成", "completed")):
            return [QueryFilter(column="orders.status", operator="=", value="completed")]
        return []

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


_TERM_ALIASES = {
    "订单": "order",
    "订单量": "order",
    "订单数": "order",
    "商品": "product",
    "产品": "product",
    "用户": "user",
    "客户": "customer",
    "学生": "student",
    "学员": "student",
    "课程": "course",
    "国家": "country",
    "地区": "country",
    "每天": "daily",
    "每日": "daily",
    "按天": "daily",
    "销量": "quantity",
    "销售量": "quantity",
    "销售额": "amount",
    "金额": "amount",
    "gmv": "amount",
    "GMV": "amount",
}


def _question_terms(text: str) -> set[str]:
    terms = _schema_terms(text)
    for source, target in _TERM_ALIASES.items():
        if source in text:
            terms.add(target)
    return terms


def _schema_terms(*parts: str) -> set[str]:
    text = " ".join(parts).lower().replace("_", " ")
    raw_terms = set(re.findall(r"[a-z][a-z0-9]*", text))
    expanded = set(raw_terms)
    for term in raw_terms:
        expanded.add(_singular(term))
    return {term for term in expanded if term}


def _singular(value: str) -> str:
    value = value.lower()
    if value.endswith("ies") and len(value) > 3:
        return f"{value[:-3]}y"
    if value.endswith("s") and len(value) > 1:
        return value[:-1]
    return value


def _ordered_unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in result:
            result.append(item)
    return result


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
