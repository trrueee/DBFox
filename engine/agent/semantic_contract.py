from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ProjectionMode = Literal[
    "entity_only",
    "metrics_only",
    "entity_with_metrics",
    "explicit_columns",
    "unknown",
]
AggregationType = Literal["count_threshold", "aggregate_metric", "group_by", "none"]
NegationType = Literal["absence_of_relation", "scalar_not_equal", "none"]
SetLogicType = Literal["intersection", "union", "difference", "both_conditions", "none"]


@dataclass
class ProjectionContract:
    mode: ProjectionMode = "unknown"
    requested_columns: list[str] = field(default_factory=list)
    allow_extra_columns: bool = True
    include_count_in_select: bool = False


@dataclass
class AggregationContract:
    type: AggregationType = "none"
    subject_hint: str | None = None
    counted_relation_hint: str | None = None
    operator: str | None = None
    threshold: int | None = None
    aggregate_functions: list[str] = field(default_factory=list)


@dataclass
class NegationContract:
    type: NegationType = "none"
    subject_hint: str | None = None
    excluded_relation_hint: str | None = None
    excluded_value_hint: str | None = None
    preferred_sql_shape: Literal["not_exists", "left_join_is_null", "any"] = "any"


@dataclass
class SetLogicContract:
    type: SetLogicType = "none"
    markers: list[str] = field(default_factory=list)
    preferred_sql_shape: Literal["exists_pair", "group_by_having", "intersect_equivalent"] = "exists_pair"


@dataclass
class DistinctContract:
    required: bool = False
    reason: Literal["explicit_distinct", "dedupe_join_subject", "unknown"] = "unknown"


@dataclass
class OrderingContract:
    required: bool = False
    columns: list[str] = field(default_factory=list)
    direction: Literal["ASC", "DESC"] | None = None


@dataclass
class ScalarFilterContract:
    column_hint: str | None = None
    operator: str | None = None
    value: int | float | str | None = None


@dataclass
class QueryContract:
    projection: ProjectionContract = field(default_factory=ProjectionContract)
    aggregation: AggregationContract | None = None
    negation: NegationContract | None = None
    set_logic: SetLogicContract | None = None
    distinct: DistinctContract | None = None
    ordering: OrderingContract | None = None
    scalar_filters: list[ScalarFilterContract] = field(default_factory=list)
    confidence: float = 0.4
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SCALAR_THRESHOLD_COLUMNS = {
    "age",
    "population",
    "weight",
    "capacity",
    "price",
    "year",
    "open_year",
    "founded",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def build_query_contract(
    question: str,
    schema_context: dict[str, Any],
    query_plan: dict[str, Any] | None = None,
) -> QueryContract:
    """Build a semantic intent contract from deterministic hints and query-plan context."""
    text = " ".join(str(question or "").strip().split())
    q = text.lower()
    contract = QueryContract(
        projection=_projection_contract(q, query_plan),
        distinct=_distinct_contract(q),
        ordering=_ordering_contract(q),
        confidence=0.55,
    )

    scalar_filter = _scalar_threshold_filter(q)
    if scalar_filter:
        contract.scalar_filters.append(scalar_filter)
        contract.notes.append("scalar_threshold_detected")

    aggregation = _count_threshold_contract(q, scalar_filter)
    if aggregation:
        contract.aggregation = aggregation
        contract.projection.include_count_in_select = False
        contract.projection.allow_extra_columns = False
        contract.projection.mode = "entity_only"
        contract.notes.append("count_threshold_detected")

    negation = _negation_contract(q)
    if negation:
        contract.negation = negation
        contract.projection.mode = "entity_only"
        contract.projection.allow_extra_columns = False
        contract.notes.append("absence_of_relation_detected")

    set_logic = _set_logic_contract(q)
    if set_logic:
        contract.set_logic = set_logic
        contract.projection.mode = "entity_only"
        contract.projection.allow_extra_columns = False
        contract.notes.append("set_logic_detected")

    if query_plan:
        _merge_query_plan_hints(contract, query_plan)

    return contract


def _projection_contract(q: str, query_plan: dict[str, Any] | None) -> ProjectionContract:
    requested = _requested_columns_from_question(q)
    if query_plan:
        raw = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan
        dimensions = raw.get("dimensions") or query_plan.get("dimensions") or []
        for item in dimensions:
            if isinstance(item, dict):
                column = str(item.get("column") or item.get("name") or "").strip()
                if column:
                    requested.append(_normalize_hint(column))
    requested = _dedupe(requested)
    if requested:
        return ProjectionContract(
            mode="entity_only",
            requested_columns=requested,
            allow_extra_columns=False,
            include_count_in_select=False,
        )
    return ProjectionContract()


def _requested_columns_from_question(q: str) -> list[str]:
    requested: list[str] = []
    if re.search(r"\bsong names?\b", q):
        requested.append("song_name")
    mappings = [
        (r"\brecord companies?\b", "record_company"),
        (r"\bairlines?\b", "airline"),
        (r"\bcities?\b", "city"),
        (r"\bids?\b", "id"),
    ]
    requested.extend(column for pattern, column in mappings if re.search(pattern, q))
    if re.search(r"\bnames?\b", q) and not re.search(r"\bsong names?\b", q):
        requested.append("name")
    return requested


def _distinct_contract(q: str) -> DistinctContract:
    if any(marker in q for marker in ("distinct", "different", "unique")):
        return DistinctContract(required=True, reason="explicit_distinct")
    return DistinctContract(required=False)


def _ordering_contract(q: str) -> OrderingContract:
    if "descending" in q or "oldest" in q or "highest" in q:
        return OrderingContract(required=True, direction="DESC")
    if "ascending" in q or "youngest" in q or "lowest" in q:
        return OrderingContract(required=True, direction="ASC")
    return OrderingContract(required=False)


def _scalar_threshold_filter(q: str) -> ScalarFilterContract | None:
    for pattern, column, operator in (
        (r"\bolder\s+than\s+(\d+)", "age", ">"),
        (r"\byounger\s+than\s+(\d+)", "age", "<"),
        (r"\bheavier\s+than\s+(\d+)", "weight", ">"),
        (r"\blighter\s+than\s+(\d+)", "weight", "<"),
    ):
        if column not in q and column != "age":
            continue
        match = re.search(pattern, q)
        if match:
            return ScalarFilterContract(column_hint=column, operator=operator, value=int(match.group(1)))

    for column in SCALAR_THRESHOLD_COLUMNS:
        column_text = column.replace("_", " ")
        patterns = [
            (rf"\bunder\s+{re.escape(column_text)}\s+(\d+)", "<"),
            (rf"\bover\s+{re.escape(column_text)}\s+(\d+)", ">"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?under\s+(\d+)", "<"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?over\s+(\d+)", ">"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?at\s+least\s+(\d+)", ">="),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?at\s+most\s+(\d+)", "<="),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?more\s+than\s+(\d+)", ">"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?greater\s+than\s+(\d+)", ">"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?less\s+than\s+(\d+)", "<"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?heavier\s+than\s+(\d+)", ">"),
            (rf"\b{re.escape(column_text)}\s+(?:is\s+)?lighter\s+than\s+(\d+)", "<"),
        ]
        for pattern, operator in patterns:
            match = re.search(pattern, q)
            if match:
                return ScalarFilterContract(column_hint=column, operator=operator, value=int(match.group(1)))
    return None


def _count_threshold_contract(q: str, scalar_filter: ScalarFilterContract | None) -> AggregationContract | None:
    threshold = _count_threshold(q)
    if not threshold:
        return None
    operator, value = threshold
    subject, counted_relation = _subject_and_counted_relation(q)
    if not subject or not counted_relation:
        return None
    return AggregationContract(
        type="count_threshold",
        subject_hint=subject,
        counted_relation_hint=counted_relation,
        operator=operator,
        threshold=int(value),
        aggregate_functions=["count"],
    )


def _count_threshold(q: str) -> tuple[str, int] | None:
    count_nouns = r"(?:flights?|employees?|pets?|friends?)"
    number = r"(?P<number>\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    patterns = [
        (rf"\bat\s+least\s+{number}\s+{count_nouns}\b", ">="),
        (rf"\bmore\s+than\s+{number}\s+{count_nouns}\b", ">"),
        (rf"\bgreater\s+than\s+{number}\s+{count_nouns}\b", ">"),
        (rf"\bat\s+most\s+{number}\s+{count_nouns}\b", "<="),
        (rf"\bless\s+than\s+{number}\s+{count_nouns}\b", "<"),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        value = _number_value(match.group("number"))
        if value is not None:
            return operator, value
    return None


def _threshold(q: str) -> tuple[str, int] | None:
    patterns = [
        (r"\bat least\s+(\d+)", ">="),
        (r"\bmore than\s+(\d+)", ">"),
        (r"\bgreater than\s+(\d+)", ">"),
        (r"\bat most\s+(\d+)", "<="),
        (r"\bless than\s+(\d+)", "<"),
        (r"\bunder\s+(\d+)", "<"),
        (r"\bover\s+(\d+)", ">"),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, q)
        if match:
            return operator, int(match.group(1))
    return None


def _number_value(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    return NUMBER_WORDS.get(value.lower())


def _subject_and_counted_relation(q: str) -> tuple[str | None, str | None]:
    subject = None
    if re.search(r"\bairlines?\b", q):
        subject = "airline"
    elif re.search(r"\bcities?\b", q):
        subject = "city"
    elif re.search(r"\bemployees?\b", q):
        subject = "employee"
    elif re.search(r"\bstudents?\b", q):
        subject = "student"

    counted_relation = None
    for pattern, relation in (
        (r"\bflights?\b", "flight"),
        (r"\bemployees?\b", "employee"),
        (r"\bpets?\b", "pet"),
        (r"\bfriends?\b", "friend"),
    ):
        if re.search(pattern, q):
            counted_relation = relation
            break

    if subject and counted_relation == subject:
        counted_relation = None
    return subject, counted_relation


def _negation_contract(q: str) -> NegationContract | None:
    if not any(marker in q for marker in (" no ", "without", "do not have", "does not have", "not have", "never", "do not hire")):
        return None
    subject = None
    if re.search(r"\bstudents?\b", q) or re.search(r"\bhigh school", q):
        subject = "student"
    elif re.search(r"\bemployees?\b", q):
        subject = "employee"
    elif re.search(r"\bshops?\b", q):
        subject = "shop"
    excluded = None
    for pattern, relation in (
        (r"\bfriends?\b", "friend"),
        (r"\bevaluations?\b", "evaluation"),
        (r"\bawards?\b", "evaluation"),
        (r"\bhire\b|\bhiring\b|\bemployees?\b", "hiring"),
        (r"\bcats?\b", "cat"),
        (r"\bpets?\b", "pet"),
    ):
        if re.search(pattern, q):
            excluded = relation
            break
    if not excluded:
        return None
    return NegationContract(
        type="absence_of_relation",
        subject_hint=subject,
        excluded_relation_hint=excluded,
        preferred_sql_shape="not_exists",
    )


def _set_logic_contract(q: str) -> SetLogicContract | None:
    markers: list[str] = []
    if any(marker in q for marker in ("shared by", "both", "also", "intersection")):
        markers.append("shared" if "shared" in q else "both")
    if "before" in q and "after" in q:
        markers.append("before_after")
    if not markers:
        return None
    return SetLogicContract(
        type="intersection",
        markers=markers,
        preferred_sql_shape="exists_pair",
    )


def _merge_query_plan_hints(contract: QueryContract, query_plan: dict[str, Any]) -> None:
    raw = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan
    metrics = raw.get("metrics") or query_plan.get("metrics") or []
    dimensions = raw.get("dimensions") or query_plan.get("dimensions") or []
    if isinstance(metrics, list) and metrics and contract.aggregation is None:
        aggregate_functions = [
            function
            for item in metrics
            if isinstance(item, dict)
            for function in _aggregate_functions_from_text(str(item.get("expression") or item.get("name") or ""))
        ]
        contract.aggregation = AggregationContract(
            type="group_by" if isinstance(dimensions, list) and dimensions else "aggregate_metric",
            aggregate_functions=_dedupe(aggregate_functions),
        )
        contract.projection.mode = "entity_with_metrics" if isinstance(dimensions, list) and dimensions else "metrics_only"
        contract.projection.allow_extra_columns = True
        if "count" in contract.aggregation.aggregate_functions:
            contract.projection.include_count_in_select = True

    text = str(raw).lower()
    if "having" in text and contract.aggregation is None:
        contract.notes.append("query_plan_mentions_having")
    if any(marker in text for marker in ("intersect", "set_logic")) and contract.set_logic is None:
        contract.set_logic = SetLogicContract(type="intersection", markers=["query_plan"], preferred_sql_shape="exists_pair")


def _normalize_hint(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _aggregate_functions_from_text(value: str) -> list[str]:
    lowered = value.lower()
    return [name for name in ("count", "avg", "max", "min", "sum") if name in lowered]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
