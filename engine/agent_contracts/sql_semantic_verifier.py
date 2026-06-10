from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

import sqlglot
from sqlglot import exp

from engine.agent_contracts.semantic_contract import QueryContract


@dataclass
class SemanticViolation:
    code: str
    severity: Literal["warning", "retryable", "blocking"]
    message: str
    expected: str | None = None
    actual: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AGGREGATES = (exp.Count, exp.Avg, exp.Max, exp.Min, exp.Sum)


def verify_sql_against_contract(
    sql: str,
    contract: QueryContract,
    schema_context: dict[str, Any],
) -> list[SemanticViolation]:
    if not sql.strip():
        return [
            SemanticViolation(
                code="sql_empty",
                severity="retryable",
                message="SQL candidate is empty.",
            )
        ]

    try:
        parsed = sqlglot.parse_one(sql, read="mysql")
    except Exception as exc:
        return [
            SemanticViolation(
                code="sql_parse_failed",
                severity="retryable",
                message=f"SQL could not be parsed: {exc}",
                actual=sql,
            )
        ]

    violations: list[SemanticViolation] = []
    violations.extend(_verify_projection(parsed, contract))
    violations.extend(_verify_distinct(parsed, contract))
    violations.extend(_verify_count_threshold(parsed, contract))
    violations.extend(_verify_scalar_filters(parsed, contract))
    violations.extend(_verify_antijoin(parsed, contract))
    violations.extend(_verify_set_logic(parsed, contract))
    return violations


def _verify_projection(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    projection = contract.projection
    if projection.mode == "unknown" and not projection.requested_columns:
        return []

    violations: list[SemanticViolation] = []
    select = _first_select(parsed)
    if not select:
        return violations
    for select in [select]:
        expressions = list(select.expressions)
        if any(_is_star_projection(item) for item in expressions):
            violations.append(
                SemanticViolation(
                    code="projection_select_star",
                    severity="retryable",
                    message="SELECT * does not satisfy an explicit projection contract.",
                    expected="explicit requested columns",
                    actual="SELECT *",
                )
            )

        if projection.mode == "entity_only":
            for item in expressions:
                if _contains_aggregate(item):
                    violations.append(
                        SemanticViolation(
                            code="projection_extra_count" if item.find(exp.Count) else "projection_extra_columns",
                            severity="retryable",
                            message="Entity-only projection should not include aggregate metrics unless requested.",
                            expected="entity columns only",
                            actual=item.sql(dialect="mysql"),
                        )
                    )

        if projection.requested_columns:
            actual_names = [_projection_name(item) for item in expressions if not _contains_aggregate(item)]
            normalized_actual = [_normalize_identifier(item) for item in actual_names if item]
            normalized_expected = [_normalize_identifier(item) for item in projection.requested_columns]

            # Detect duplicate aliases for the same underlying column
            _check_duplicate_aliases(expressions, violations)

            for expected in normalized_expected:
                if expected not in normalized_actual:
                    violations.append(
                        SemanticViolation(
                            code="projection_missing_requested_column",
                            severity="retryable",
                            message="SQL projection is missing a requested column.",
                            expected=expected,
                            actual=", ".join(actual_names),
                        )
                    )
            if not projection.allow_extra_columns:
                extras = [name for name in normalized_actual if name not in normalized_expected]
                if extras:
                    violations.append(
                        SemanticViolation(
                            code="projection_extra_columns",
                            severity="retryable",
                            message="SQL projection includes extra entity columns.",
                            expected=", ".join(projection.requested_columns),
                            actual=", ".join(actual_names),
                        )
                    )
            if (
                len(normalized_expected) > 1
                and normalized_actual[: len(normalized_expected)] != normalized_expected
            ):
                violations.append(
                    SemanticViolation(
                        code="projection_order_mismatch",
                        severity="warning",
                        message="Projection order differs from the requested column order.",
                        expected=", ".join(projection.requested_columns),
                        actual=", ".join(actual_names),
                    )
                )

    return violations


def _verify_distinct(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    distinct = contract.distinct
    if not distinct or not distinct.required:
        return []
    select = _first_select(parsed)
    if not select or select.args.get("distinct"):
        return []
    # GROUP BY already deduplicates rows — no DISTINCT needed
    group = select.args.get("group")
    if group and getattr(group, "expressions", None):
        return []
    # Aggregation without GROUP BY (e.g. COUNT(*)) does not need DISTINCT
    if not group and _has_aggregate_in_select(select):
        return []
    return [
        SemanticViolation(
            code="distinct_missing",
            severity="retryable",
            message="The question explicitly asks for distinct/different values, but SQL does not use DISTINCT.",
            expected="SELECT DISTINCT ...",
            actual=select.sql(dialect="mysql"),
        )
    ]


def _has_aggregate_in_select(select: exp.Select) -> bool:
    """Check if SELECT has aggregate functions (COUNT, AVG, etc.) without GROUP BY."""
    for item in select.expressions:
        if _contains_aggregate(item):
            return True
    return False


def _verify_count_threshold(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    aggregation = contract.aggregation
    if not aggregation or aggregation.type != "count_threshold":
        return []

    select = _first_select(parsed)
    if not select:
        return []

    violations: list[SemanticViolation] = []
    group = select.args.get("group")
    having = select.args.get("having")
    if not group or not getattr(group, "expressions", None):
        violations.append(
            SemanticViolation(
                code="group_by_missing",
                severity="retryable",
                message="Count-threshold contracts require GROUP BY over the subject.",
                expected="GROUP BY subject",
            )
        )
    if not having:
        violations.append(
            SemanticViolation(
                code="having_missing",
                severity="retryable",
                message="Count-threshold contracts require HAVING.",
                expected="HAVING COUNT(...) threshold",
            )
        )
        return violations

    if not having.find(exp.Count):
        violations.append(
            SemanticViolation(
                code="having_count_missing",
                severity="retryable",
                message="HAVING clause must contain COUNT for a related-row threshold.",
                expected="COUNT(...) in HAVING",
                actual=having.sql(dialect="mysql"),
            )
        )

    threshold = _having_count_threshold(having)
    if threshold and aggregation.operator and aggregation.threshold is not None:
        operator, value = threshold
        if operator != aggregation.operator or value != aggregation.threshold:
            violations.append(
                SemanticViolation(
                    code="having_threshold_mismatch",
                    severity="retryable",
                    message="HAVING threshold does not match the query contract.",
                    expected=f"{aggregation.operator} {aggregation.threshold}",
                    actual=f"{operator} {value}",
                )
            )
    return violations


def _verify_scalar_filters(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    if not contract.scalar_filters:
        return []
    violations: list[SemanticViolation] = []
    select = _first_select(parsed)
    if not select:
        return violations
    having = select.args.get("having")
    if having and not having.find(*AGGREGATES):
        violations.append(
            SemanticViolation(
                code="having_should_be_where",
                severity="retryable",
                message="Scalar field thresholds should be represented in WHERE, not HAVING.",
                expected="WHERE scalar_column threshold",
                actual=having.sql(dialect="mysql"),
            )
        )
    return violations


def _verify_antijoin(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    negation = contract.negation
    if not negation or negation.type != "absence_of_relation":
        return []
    relation = _normalize_relation(negation.excluded_relation_hint or "")
    if not relation:
        return []

    # Detect <> x OR IS NULL anti-pattern — always wrong for absence queries
    antijoin_bad = _detect_antijoin_not_equal_or_null(parsed)
    if antijoin_bad:
        return [antijoin_bad]

    has_not_exists = _has_not_exists_for_relation(parsed, relation)
    has_except = _has_except(parsed)
    has_left_join_null = _has_left_join_null_antijoin(parsed, relation)

    # When the negation contract specifies an excluded value (e.g. "cat pet"),
    # LEFT JOIN ... AND value WHERE IS NULL is unreliable — subjects with
    # multiple related rows (one matching value, one not) will still appear.
    # Only NOT EXISTS guarantees correct anti-join for value-qualified absence.
    if negation.excluded_value_hint and not has_not_exists and not has_except:
        return [
            SemanticViolation(
                code="antijoin_missing",
                severity="retryable",
                message=(
                    "For value-qualified absence (e.g. 'no cat pet'), LEFT JOIN patterns "
                    "are unreliable when the subject may have multiple related rows. "
                    "Use NOT EXISTS with a correlated subquery that checks the specific value."
                ),
                expected="NOT EXISTS (SELECT 1 FROM relation WHERE ... AND attr = value AND key = outer.key)",
                actual=parsed.sql(dialect="mysql"),
            )
        ]

    if has_except or has_not_exists or has_left_join_null:
        return []

    select = _first_select(parsed)
    if select and _directly_joins_relation(select, relation):
        return [
            SemanticViolation(
                code="antijoin_outer_join",
                severity="retryable",
                message="Absence-of-relation queries should not inner join the excluded relation in the outer scope.",
                expected="NOT EXISTS or LEFT JOIN ... IS NULL",
                actual=select.sql(dialect="mysql"),
            )
        ]

    return [
        SemanticViolation(
            code="antijoin_missing",
            severity="retryable",
            message="SQL does not contain an anti-join shape for the absence contract.",
            expected="NOT EXISTS, LEFT JOIN IS NULL, or EXCEPT equivalent",
            actual=parsed.sql(dialect="mysql"),
        )
    ]


def _detect_antijoin_not_equal_or_null(parsed: exp.Expression) -> SemanticViolation | None:
    """Detect the broken anti-join pattern:
    LEFT JOIN relation ... WHERE relation.attr <> value OR relation.attr IS NULL
    This is always wrong for absence queries — it preserves subjects that have
    a matching row AND a non-matching row.
    """
    select = _first_select(parsed)
    if not select:
        return None
    where = select.args.get("where")
    if not where:
        return None

    # Look for (col <> value OR col IS NULL) pattern
    for or_node in where.find_all(exp.Or):
        has_not_equal = False
        has_is_null = False
        neq_column: str | None = None
        null_column: str | None = None

        for child in [or_node.left, or_node.right]:
            if isinstance(child, exp.NEQ):
                has_not_equal = True
                if isinstance(child.left, exp.Column):
                    neq_column = child.left.name
            elif isinstance(child, exp.Is):
                if isinstance(child.expression, exp.Null):
                    has_is_null = True
                    if isinstance(child.this, exp.Column):
                        null_column = child.this.name

        if has_not_equal and has_is_null:
            # Verify columns are the same or from same table
            if neq_column and null_column and neq_column == null_column:
                return SemanticViolation(
                    code="antijoin_not_equal_or_null",
                    severity="retryable",
                    message=(
                        "LEFT JOIN ... WHERE col <> value OR col IS NULL does not correctly "
                        "express absence. Subjects with both a matching and non-matching related "
                        "row will still appear in results. Use NOT EXISTS or a restricted LEFT JOIN "
                        "to the excluded value only."
                    ),
                    expected="NOT EXISTS (SELECT 1 FROM relation WHERE ... AND attr = value) or LEFT JOIN restricted subquery",
                    actual=or_node.sql(dialect="mysql"),
                )

    return None


def _verify_set_logic(parsed: exp.Expression, contract: QueryContract) -> list[SemanticViolation]:
    set_logic = contract.set_logic
    if not set_logic or set_logic.type not in {"intersection", "both_conditions"}:
        return []

    violations: list[SemanticViolation] = []
    if _has_same_scope_contradictory_threshold(parsed):
        violations.append(
            SemanticViolation(
                code="setlogic_contradictory_and",
                severity="retryable",
                message="Intersection/shared semantics cannot be represented as contradictory predicates in one row scope.",
                expected="EXISTS pair, GROUP BY/HAVING, or INTERSECT equivalent",
                actual=parsed.sql(dialect="mysql"),
            )
        )

    if _has_intersect(parsed) or _has_exists_pair(parsed) or _has_group_having_intersection(parsed):
        return violations

    violations.append(
        SemanticViolation(
            code="setlogic_missing",
            severity="retryable",
            message="SQL does not express required set/intersection semantics.",
            expected="EXISTS pair, GROUP BY/HAVING, or INTERSECT equivalent",
            actual=parsed.sql(dialect="mysql"),
        )
    )
    return violations


def _is_star_projection(item: exp.Expression) -> bool:
    inner = item.this if isinstance(item, exp.Alias) else item
    return isinstance(inner, exp.Star) or (
        isinstance(inner, exp.Column) and isinstance(inner.this, exp.Star)
    )


def _check_duplicate_aliases(
    expressions: list[exp.Expression],
    violations: list[SemanticViolation],
) -> None:
    """Detect the same underlying column selected multiple times with different aliases.

    Example: SELECT a.Airline AS airline, a.Airline AS airlines_airline
    → projection_duplicate_alias
    """
    column_sources: dict[str, list[str]] = {}
    for item in expressions:
        if isinstance(item, exp.Alias):
            inner = item.this
            # Build a key from table.column of the underlying expression
            if isinstance(inner, exp.Column):
                key = f"{inner.table or ''}.{inner.name}".lower()
            else:
                key = inner.sql(dialect="mysql").lower()
            alias = item.alias.lower() if item.alias else ""
            column_sources.setdefault(key, []).append(alias)
        elif isinstance(item, exp.Column):
            key = f"{item.table or ''}.{item.name}".lower()
            column_sources.setdefault(key, []).append(key)

    for key, aliases in column_sources.items():
        unique_aliases = set(a for a in aliases if a)
        if len(unique_aliases) > 1:
            violations.append(
                SemanticViolation(
                    code="projection_duplicate_alias",
                    severity="retryable",
                    message=(
                        f"Same underlying column '{key}' selected multiple times "
                        f"with different aliases: {', '.join(sorted(unique_aliases))}"
                    ),
                    expected="single alias for each column",
                    actual=", ".join(sorted(unique_aliases)),
                )
            )


def _contains_aggregate(item: exp.Expression) -> bool:
    return any(item.find(kind) is not None for kind in AGGREGATES)


def _projection_name(item: exp.Expression) -> str:
    if isinstance(item, exp.Distinct):
        expressions = list(item.expressions)
        return _projection_name(expressions[0]) if expressions else ""
    if isinstance(item, exp.Alias) and item.alias:
        return str(item.alias)
    if isinstance(item, exp.Column):
        return item.name
    if isinstance(item, exp.Identifier):
        return item.name
    return str(getattr(item, "alias_or_name", "") or item.sql(dialect="mysql"))


def _first_select(parsed: exp.Expression) -> exp.Select | None:
    if isinstance(parsed, exp.Select):
        return parsed
    return next(parsed.find_all(exp.Select), None)


def _having_count_threshold(having: exp.Expression) -> tuple[str, int] | None:
    compare_types: tuple[type[exp.Expression], ...] = (exp.GTE, exp.GT, exp.LTE, exp.LT, exp.EQ)
    operators = {
        exp.GTE: ">=",
        exp.GT: ">",
        exp.LTE: "<=",
        exp.LT: "<",
        exp.EQ: "=",
    }
    for compare_type in compare_types:
        for node in having.find_all(compare_type):
            if not node.find(exp.Count):
                continue
            literal = _numeric_literal(node.right) or _numeric_literal(node.left)
            if literal is not None:
                return operators[compare_type], literal
    return None


def _numeric_literal(node: exp.Expression | None) -> int | None:
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(str(node.this))
        except ValueError:
            return None
    return None


def _has_except(parsed: exp.Expression) -> bool:
    return isinstance(parsed, exp.Except) or any(True for _ in parsed.find_all(exp.Except))


def _has_intersect(parsed: exp.Expression) -> bool:
    return isinstance(parsed, exp.Intersect) or any(True for _ in parsed.find_all(exp.Intersect))


def _has_exists_pair(parsed: exp.Expression) -> bool:
    return sum(1 for _ in parsed.find_all(exp.Exists)) >= 2


def _has_not_exists_for_relation(parsed: exp.Expression, relation: str) -> bool:
    for node in parsed.find_all(exp.Exists):
        if not _expression_mentions_relation(node, relation):
            continue
        parent = node.parent
        while parent is not None:
            if isinstance(parent, exp.Not):
                return True
            if isinstance(parent, exp.Select):
                break
            parent = parent.parent
    return False


def _has_left_join_null_antijoin(parsed: exp.Expression, relation: str) -> bool:
    select = _first_select(parsed)
    if not select:
        return False
    aliases: set[str] = set()
    for join in select.args.get("joins") or []:
        table = join.this
        if not isinstance(table, exp.Table) or not _relation_matches(table.name, relation):
            continue
        side = str(join.args.get("side") or "").lower()
        if side == "left":
            aliases.add(str(table.alias_or_name).lower())
            aliases.add(table.name.lower())
    if not aliases:
        return False
    where = select.args.get("where")
    if not where:
        return False
    for node in where.find_all(exp.Is):
        if not isinstance(node.expression, exp.Null):
            continue
        column = node.this
        if isinstance(column, exp.Column) and str(column.table).lower() in aliases:
            return True
    return False


def _directly_joins_relation(select: exp.Select, relation: str) -> bool:
    for join in select.args.get("joins") or []:
        table = join.this
        if isinstance(table, exp.Table) and _relation_matches(table.name, relation):
            side = str(join.args.get("side") or "").lower()
            if side != "left":
                return True
    return False


def _expression_mentions_relation(node: exp.Expression, relation: str) -> bool:
    return any(_relation_matches(table.name, relation) for table in node.find_all(exp.Table))


def _has_group_having_intersection(parsed: exp.Expression) -> bool:
    select = _first_select(parsed)
    if not select:
        return False
    return bool(select.args.get("group") and select.args.get("having") and select.args["having"].find(exp.Count))


def _has_same_scope_contradictory_threshold(parsed: exp.Expression) -> bool:
    for select in parsed.find_all(exp.Select):
        where = select.args.get("where")
        if not where:
            continue
        comparisons: dict[str, dict[str, set[int]]] = {}
        for node in where.walk():
            if not isinstance(node, (exp.LT, exp.LTE, exp.GT, exp.GTE)):
                continue
            if _nearest_select(node) is not select:
                continue
            column, operator, value = _comparison_parts(node)
            if not column or value is None:
                continue
            bucket = comparisons.setdefault(column, {"lt": set(), "gt": set()})
            if operator in {"<", "<="}:
                bucket["lt"].add(value)
            elif operator in {">", ">="}:
                bucket["gt"].add(value)
        for values in comparisons.values():
            if values["lt"] and values["gt"]:
                return True
    return False


def _nearest_select(node: exp.Expression) -> exp.Select | None:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.Select):
            return parent
        parent = parent.parent
    return None


def _comparison_parts(node: exp.Expression) -> tuple[str | None, str | None, int | None]:
    operator_map = {
        exp.LT: "<",
        exp.LTE: "<=",
        exp.GT: ">",
        exp.GTE: ">=",
    }
    left = node.left
    right = node.right
    if isinstance(left, exp.Column):
        return _normalize_identifier(left.name), operator_map[type(node)], _numeric_literal(right)
    if isinstance(right, exp.Column):
        inverse = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}
        operator = operator_map[type(node)]
        return _normalize_identifier(right.name), inverse[operator], _numeric_literal(left)
    return None, None, None


def _normalize_identifier(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    if text.endswith("s") and len(text) > 3:
        text = text[:-1]
    return text


def _normalize_relation(value: str) -> str:
    text = _normalize_identifier(value)
    aliases = {
        "highschooler": "student",
        "highschoolers": "student",
        "friends": "friend",
        "flights": "flight",
        "airlines": "airline",
        "evaluations": "evaluation",
        "employees": "employee",
        "shops": "shop",
        "hiring": "hiring",
    }
    return aliases.get(text, text)


def _relation_matches(table_name: str, relation: str) -> bool:
    table = _normalize_relation(table_name)
    target = _normalize_relation(relation)
    return table == target or table.endswith(target)
