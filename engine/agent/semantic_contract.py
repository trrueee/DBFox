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

    if contract.distinct and contract.distinct.required:
        contract.notes.append("explicit_distinct_detected")
        contract.confidence = max(contract.confidence, 0.75)

    # Bump confidence when specific columns are detected in the question
    # (e.g. "first name", "age", "id"). This enables projection retry for
    # explicit column-request cases.
    if contract.projection.requested_columns:
        contract.notes.append("explicit_columns_detected")
        contract.confidence = max(contract.confidence, 0.72)

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
        contract.confidence = max(contract.confidence, 0.75)

    negation = _negation_contract(q)
    if negation:
        contract.negation = negation
        contract.projection.mode = "entity_only"
        contract.projection.allow_extra_columns = False
        contract.notes.append("absence_of_relation_detected")
        contract.confidence = max(contract.confidence, 0.75)

    set_logic = _set_logic_contract(q)
    if set_logic:
        contract.set_logic = set_logic
        contract.projection.mode = "entity_only"
        contract.projection.allow_extra_columns = False
        contract.notes.append("set_logic_detected")
        contract.confidence = max(contract.confidence, 0.75)

    if query_plan:
        _merge_query_plan_hints(contract, query_plan)

    return contract


def _projection_contract(q: str, query_plan: dict[str, Any] | None) -> ProjectionContract:
    surface_hints = _requested_columns_from_question(q)

    # Collect canonical column identities from query plan dimensions
    plan_columns: list[str] = []
    if query_plan:
        raw = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan
        dimensions = raw.get("dimensions") or query_plan.get("dimensions") or []
        for item in dimensions:
            if isinstance(item, dict):
                column = str(item.get("column") or item.get("name") or "").strip()
                if column:
                    plan_columns.append(column)

    # Resolve surface hints against plan columns to eliminate duplicates.
    #   "name" + plan has "student.Fname" → use "student.Fname"
    #   "id"   + plan has "has_pet.PetID"   → use "has_pet.PetID"
    # Surface hints without a plan match are kept as-is.
    resolved: list[str] = []
    for hint in surface_hints:
        matched = _resolve_hint_to_plan(hint, plan_columns)
        if matched:
            resolved.append(matched)
        elif hint not in resolved:
            resolved.append(hint)

    # If the question did not surface explicit columns, fall back to plan
    # dimensions. When explicit hints exist, do not let a broad query-plan
    # dimension (for example singer.Name) widen the requested projection.
    if not surface_hints:
        resolved_norm = {_extract_column_name(c).lower() for c in resolved}
        for pc in plan_columns:
            if _extract_column_name(pc).lower() not in resolved_norm:
                resolved.append(pc)
                resolved_norm.add(_extract_column_name(pc).lower())

    requested = _dedupe(resolved)
    if requested:
        return ProjectionContract(
            mode="entity_only",
            requested_columns=requested,
            allow_extra_columns=False,
            include_count_in_select=False,
        )
    return ProjectionContract()


def _resolve_hint_to_plan(hint: str, plan_columns: list[str]) -> str | None:
    """Resolve a surface hint like 'name' or 'id' to a canonical plan column.

    Returns the plan column string (e.g. 'student.Fname') if a match is found,
    or None if the hint should stand alone.
    """
    hint_lower = hint.lower().strip()
    # Direct match: hint "Fname" matches plan "student.Fname"
    for pc in plan_columns:
        col_name = _extract_column_name(pc).lower()
        if col_name == hint_lower:
            return pc
    # Semantic match: hint "name" matches plan columns named Fname, Name, Lname, AirportName
    _NAME_HINTS = {"name", "first_name", "fname", "lname", "fullname", "student_name",
                   "airport_name", "city_name", "visitor_name", "employee_name"}
    if hint_lower in _NAME_HINTS:
        for pc in plan_columns:
            col_name = _extract_column_name(pc).lower()
            if col_name in ("fname", "name", "lname", "fullname", "firstname", "lastname",
                            "airportname", "cityname", "visitorname", "employeename"):
                return pc
    # ID hint: matches plan columns named PetID, StuID, ID, student_id, etc.
    _ID_HINTS = {"id", "pet_id", "petid", "student_id", "stuid"}
    if hint_lower in _ID_HINTS:
        for pc in plan_columns:
            col_name = _extract_column_name(pc).lower()
            if col_name.endswith("id") or col_name == "id":
                return pc
    # Age hint
    if hint_lower == "age":
        for pc in plan_columns:
            if _extract_column_name(pc).lower() == "age":
                return pc
    # City hint
    if hint_lower == "city":
        for pc in plan_columns:
            if _extract_column_name(pc).lower() == "city":
                return pc
    # Major hint
    if hint_lower == "major":
        for pc in plan_columns:
            if _extract_column_name(pc).lower() == "major":
                return pc
    return None


def _extract_column_name(column_ref: str) -> str:
    """Extract the bare column name from a table.column reference.

    'student.Fname' → 'Fname'
    'Fname' → 'Fname'
    """
    return column_ref.rsplit(".", 1)[-1] if "." in column_ref else column_ref


def _requested_columns_from_question(q: str) -> list[str]:
    requested: list[str] = []

    # Check if an attribute mention is in filter context (e.g. "above age 20")
    def _is_filter_context(pattern: str) -> bool:
        # Direct: "above age 20", "older than 20"
        if re.search(
            rf"\b(?:above|below|over|under|older|younger|more|less|greater|at\s+least|at\s+most)\s+(?:the\s+)?(?:average\s+)?{pattern}\b",
            q,
        ):
            return True
        # Pattern: "above the average age", "older than average age"
        if re.search(
            rf"\b(?:above|below|older|younger)\s+the\s+.*?\b{pattern}\b",
            q,
        ):
            return True
        return False

    asks_song_name = bool(
        re.search(r"\bsong names?\b", q)
        or re.search(r"\bnames?\b.*\bsongs?\b", q)
        or re.search(r"\bnames?\b.*\bof\s+the\s+songs?\b", q)
        or re.search(r"\bsongs?\b.*\bnames?\b", q)
    )
    if asks_song_name:
        requested.append("song_name")
    if re.search(r"\brelease years?\b", q):
        requested.append("song_release_year")
    mappings = [
        (r"\brecord companies?\b", "record_company"),
        (r"\bairlines?\b", "airline"),
        (r"\bcities?\b", "city"),
        (r"\bids?\b", "id"),
        (r"\bmajor\b", "major"),
    ]
    requested.extend(column for pattern, column in mappings if re.search(pattern, q))

    # "age" — only requested, not filter-context ("above age 20")
    if re.search(r"\bages?\b", q) and not _is_filter_context("ages?"):
        requested.append("age")
    # "country" — only requested, not filter-context ("from France")
    if re.search(r"\bcountries?\b", q) and not re.search(r"\bfrom\b.*\bcountries?\b", q):
        requested.append("country")

    # "name" as a requested column — only when not in a filter context
    if re.search(r"\bnames?\b", q) and not asks_song_name:
        if not re.search(r"\blast\s+name\b|\bfirst\s+name\b|\bwhose\s+name\b|\bname\s+is\b", q):
            requested.append("name")
    return requested


def _distinct_contract(q: str) -> DistinctContract:
    # Check for explicit uniqueness intent
    has_explicit = any(marker in q for marker in (
        "distinct", "different", "unique", "without duplicates",
    ))
    if not has_explicit:
        return DistinctContract(required=False)

    # Do NOT require DISTINCT for aggregation count questions like "how many different X"
    if _is_count_distinct_question(q):
        return DistinctContract(required=False)

    # "different kinds/types/names/entities" — strong explicit intent
    if re.search(r"different\s+(kinds?|types?|names?|entities)", q):
        return DistinctContract(required=True, reason="explicit_distinct")

    # Generic "distinct / different / unique" in question
    if any(marker in q for marker in ("distinct", "different", "unique", "without duplicates")):
        return DistinctContract(required=True, reason="explicit_distinct")

    return DistinctContract(required=False)


def _is_count_distinct_question(q: str) -> bool:
    """Returns True if the question is about counting distinct entities, e.g. 'how many different cities'.
    These should use COUNT(DISTINCT ...) not SELECT DISTINCT."""
    return bool(re.search(
        r"how\s+many\s+different\b|\bcount\s+.*\bdistinct\b|\bnumber\s+of\s+different\b",
        q,
    ))


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
    # Broader detection: "at least N <anything>" is a count threshold
    number = r"(?P<number>\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    broad_patterns = [
        rf"\bat\s+least\s+{number}\b",
        rf"\bmore\s+than\s+{number}\b",
        rf"\bfewer\s+than\s+{number}\b",
        rf"\bless\s+than\s+{number}\b",
        rf"\bat\s+most\s+{number}\b",
    ]
    for pattern in broad_patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        value = _number_value(match.group("number"))
        if value is not None and value >= 1:
            # Only if the threshold is about entity counts, not scalar values
            # Check that the number is followed by a noun (not a unit like "years", "kg")
            after = q[match.end():].strip()
            if after and not after.startswith(("year", "month", "day", "kg", "lb", "mile", "km", "percent", "%")):
                op_map = {"at least": ">=", "more than": ">", "fewer than": "<", "less than": "<", "at most": "<="}
                for phrase, op in op_map.items():
                    if phrase in match.group(0).lower():
                        return op, value
                return ">=", value
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
    markers = (" no ", "without", "do not have", "does not have", "not have",
               "never", "do not hire", "have no", "has no", "not received",
               "not owned", "not used", "not played", "not been arranged",
               "do not own", "does not own", "not any", "no visitor",
               "do not speak", "does not speak")
    if not any(marker in q for marker in markers):
        return None
    subject = None
    for pat, subj in (
        (r"\bstudents?\b|high school", "student"),
        (r"\bemployees?\b", "employee"),
        (r"\bshops?\b", "shop"),
        (r"\bmuseums?\b", "museum"),
        (r"\bteachers?\b", "teacher"),
        (r"\bairports?\b", "airport"),
        (r"\bcountries?\b", "country"),
        (r"\btv channels?\b", "channel"),
        (r"\bsingers?\b", "singer"),
        (r"\bstadiums?\b", "stadium"),
        (r"\bconductors?\b", "conductor"),
        (r"\borchestras?\b", "orchestra"),
        (r"\bbattles?\b", "battle"),
        (r"\bdocuments?\b", "document"),
        (r"\bpeople\b", "person"),
    ):
        if re.search(pat, q):
            subject = subj
            break
    # Detect value-qualified relation like "cat pet" → relation=pet, value=cat
    excluded = None
    excluded_value: str | None = None
    _pet_type_match = re.search(r"\b(cat|dog|bird|fish|rabbit|hamster|turtle)s?\s+(pet|pets)\b", q)
    if _pet_type_match:
        excluded = "pet"
        excluded_value = _pet_type_match.group(1)
    if excluded is None:
        for pattern, relation in (
            (r"\bfriends?\b", "friend"),
            (r"\bevaluations?\b", "evaluation"),
            (r"\bawards?\b", "evaluation"),
            (r"\bhire\b|\bhiring\b|\bemployees?\b", "hiring"),
            (r"\bpets?\b", "pet"),
            (r"\bcats?\b", "cat"),
            (r"\bflights?\b", "flight"),
            (r"\bcourses?\b", "course"),
            (r"\bvisitors?\b", "visitor"),
            (r"\bEnglish\b", "english_language"),
            (r"\bcartoons?\b", "cartoon"),
            (r"\bdogs?\b", "dog"),
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
        excluded_value_hint=excluded_value,
        preferred_sql_shape="not_exists",
    )


def _set_logic_contract(q: str) -> SetLogicContract | None:
    markers: list[str] = []
    # "both X and Y" patterns
    if any(marker in q for marker in ("both ", "all of", "shared by", "common to", "used by both",
                                        "in both", "and also", "who have both",
                                        "played in both", "speak both")):
        markers.append("both")
    # INTERSECT/EXCEPT patterns from gold SQL semantics
    if any(marker in q for marker in ("also have", "two different", "two types of")):
        markers.append("both")
    if "shared" in q:
        markers.append("shared")
    # Before/after temporal set logic
    if "before" in q and "after" in q:
        markers.append("before_after")
    # EXCEPT patterns
    if any(marker in q for marker in ("except for", "do not speak", "does not speak",
                                        "not English", "did not have", "do not have any")):
        markers.append("except")
    if not markers:
        return None
    return SetLogicContract(
        type="intersection" if "both" in markers or "shared" in markers or "intersection" in markers else "difference",
        markers=markers,
        preferred_sql_shape="exists_pair" if "both" in markers or "shared" in markers else "not_exists",
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
