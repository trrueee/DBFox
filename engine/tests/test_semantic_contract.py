from __future__ import annotations

from engine.agent.semantic_contract import build_query_contract


def test_builds_count_threshold_contract_without_projecting_count() -> None:
    contract = build_query_contract(
        "Which airlines have at least 10 flights?",
        schema_context={},
        query_plan=None,
    )

    assert contract.aggregation is not None
    assert contract.aggregation.type == "count_threshold"
    assert contract.aggregation.subject_hint == "airline"
    assert contract.aggregation.counted_relation_hint == "flight"
    assert contract.aggregation.operator == ">="
    assert contract.aggregation.threshold == 10
    assert contract.projection.mode == "entity_only"
    assert contract.projection.include_count_in_select is False


def test_builds_count_threshold_with_scalar_filter() -> None:
    contract = build_query_contract(
        "Which cities do more than one employee under age 30 come from?",
        schema_context={},
        query_plan=None,
    )

    assert contract.aggregation is not None
    assert contract.aggregation.type == "count_threshold"
    assert contract.aggregation.subject_hint == "city"
    assert contract.aggregation.counted_relation_hint == "employee"
    assert contract.aggregation.operator == ">"
    assert contract.aggregation.threshold == 1
    assert len(contract.scalar_filters) == 1
    assert contract.scalar_filters[0].column_hint == "age"
    assert contract.scalar_filters[0].operator == "<"
    assert contract.scalar_filters[0].value == 30


def test_builds_scalar_threshold_as_filter_not_count_threshold() -> None:
    contract = build_query_contract(
        "Cities with population at least 1000000",
        schema_context={},
        query_plan=None,
    )

    assert contract.aggregation is None or contract.aggregation.type != "count_threshold"
    assert len(contract.scalar_filters) == 1
    assert contract.scalar_filters[0].column_hint == "population"
    assert contract.scalar_filters[0].operator == ">="
    assert contract.scalar_filters[0].value == 1000000


def test_query_plan_metric_projection_is_not_entity_only() -> None:
    contract = build_query_contract(
        "Show all countries and the number of singers in each country.",
        schema_context={},
        query_plan={
            "metrics": [{"name": "singer_count", "expression": "COUNT(*)"}],
            "dimensions": [{"name": "country", "column": "Country"}],
        },
    )

    assert contract.aggregation is not None
    assert contract.aggregation.type == "group_by"
    assert contract.projection.mode == "entity_with_metrics"
    assert contract.projection.include_count_in_select is True
    assert contract.projection.allow_extra_columns is True


def test_song_names_projection_prefers_song_name_column() -> None:
    contract = build_query_contract(
        "List all song names by singers above the average age.",
        schema_context={},
        query_plan=None,
    )

    assert contract.projection.requested_columns == ["song_name"]
    assert contract.projection.allow_extra_columns is False


def test_song_name_and_release_year_do_not_request_singer_name() -> None:
    contract = build_query_contract(
        "Show the name and the release year of the song by the youngest singer.",
        schema_context={},
        query_plan={
            "dimensions": [
                {"name": "name", "column": "Name"},
                {"name": "song_name", "column": "Song_Name"},
                {"name": "song_release_year", "column": "Song_release_year"},
            ],
        },
    )

    assert contract.projection.requested_columns == ["Song_Name", "Song_release_year"]
    assert contract.projection.allow_extra_columns is False


def test_builds_absence_of_relation_contract_for_no_friends() -> None:
    contract = build_query_contract(
        "Students with no friends",
        schema_context={},
        query_plan=None,
    )

    assert contract.negation is not None
    assert contract.negation.type == "absence_of_relation"
    assert contract.negation.subject_hint == "student"
    assert contract.negation.excluded_relation_hint == "friend"
    assert contract.negation.preferred_sql_shape == "not_exists"


def test_builds_set_logic_contract_for_shared_by_before_and_after() -> None:
    contract = build_query_contract(
        "Record companies shared by orchestras founded before and after 2003",
        schema_context={},
        query_plan=None,
    )

    assert contract.set_logic is not None
    assert contract.set_logic.type == "intersection"
    assert "shared" in contract.set_logic.markers
    assert "before_after" in contract.set_logic.markers
    assert contract.set_logic.preferred_sql_shape == "exists_pair"
    assert contract.projection.requested_columns == ["record_company"]
