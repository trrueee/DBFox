from __future__ import annotations

from engine.agent_contracts.semantic_contract import build_query_contract
from engine.agent_contracts.sql_semantic_verifier import verify_sql_against_contract


def _codes(sql: str, question: str) -> set[str]:
    contract = build_query_contract(question, schema_context={}, query_plan=None)
    return {
        violation.code
        for violation in verify_sql_against_contract(
            sql,
            contract,
            schema_context={},
        )
    }


def test_count_threshold_requires_having_count_threshold() -> None:
    question = "Which airlines have at least 10 flights?"

    assert "having_missing" in _codes(
        "SELECT Airline FROM flights GROUP BY Airline",
        question,
    )
    assert {"having_missing", "projection_extra_count"}.issubset(
        _codes("SELECT Airline, COUNT(*) FROM flights GROUP BY Airline", question)
    )
    assert not _codes(
        "SELECT Airline FROM flights GROUP BY Airline HAVING COUNT(*) >= 10",
        question,
    )


def test_scalar_threshold_uses_where_not_count_threshold_having() -> None:
    question = "Cities with population at least 1000000"

    assert not _codes(
        "SELECT city FROM city WHERE population >= 1000000",
        question,
    )


def test_group_by_metric_projection_is_allowed() -> None:
    contract = build_query_contract(
        "Show all countries and the number of singers in each country.",
        schema_context={},
        query_plan={
            "metrics": [{"name": "singer_count", "expression": "COUNT(*)"}],
            "dimensions": [{"name": "country", "column": "Country"}],
        },
    )

    assert not verify_sql_against_contract(
        "SELECT Country, COUNT(*) FROM singer GROUP BY Country",
        contract,
        schema_context={},
    )


def test_max_metric_projection_is_allowed() -> None:
    contract = build_query_contract(
        "Find the maximum weight for each type of pet. List the maximum weight and pet type.",
        schema_context={},
        query_plan={
            "metrics": [{"name": "max_weight", "expression": "MAX(weight)"}],
            "dimensions": [{"name": "pet_type", "column": "PetType"}],
        },
    )

    assert not verify_sql_against_contract(
        "SELECT PetType, MAX(weight) FROM pets GROUP BY PetType",
        contract,
        schema_context={},
    )


def test_song_names_rejects_extra_singer_name_projection() -> None:
    contract = build_query_contract(
        "List all song names by singers above the average age.",
        schema_context={},
        query_plan=None,
    )

    codes = {
        violation.code
        for violation in verify_sql_against_contract(
            "SELECT name, song_name FROM singer WHERE Age > (SELECT AVG(Age) FROM singer)",
            contract,
            schema_context={},
        )
    }

    assert "projection_extra_columns" in codes


def test_antijoin_rejects_outer_join_to_excluded_relation() -> None:
    question = "Students with no friends"

    assert "antijoin_outer_join" in _codes(
        "SELECT h.name FROM highschooler AS h JOIN friend AS f ON h.ID = f.student_id",
        question,
    )
    assert not _codes(
        "SELECT h.name FROM highschooler AS h "
        "WHERE NOT EXISTS (SELECT 1 FROM friend AS f WHERE f.student_id = h.ID)",
        question,
    )


def test_set_logic_rejects_contradictory_same_scope_conditions() -> None:
    question = "Record companies shared by orchestras founded before and after 2003"

    assert "setlogic_contradictory_and" in _codes(
        "SELECT Record_Company FROM orchestra "
        "WHERE Year_of_Founded < 2003 AND Year_of_Founded > 2003",
        question,
    )
    assert not _codes(
        "SELECT DISTINCT o.Record_Company FROM orchestra AS o "
        "WHERE EXISTS (SELECT 1 FROM orchestra AS before_o "
        "WHERE before_o.Record_Company = o.Record_Company "
        "AND before_o.Year_of_Founded < 2003) "
        "AND EXISTS (SELECT 1 FROM orchestra AS after_o "
        "WHERE after_o.Record_Company = o.Record_Company "
        "AND after_o.Year_of_Founded > 2003)",
        question,
    )


def test_projection_flags_select_star_and_extra_count() -> None:
    assert "projection_select_star" in _codes(
        "SELECT * FROM flights",
        "Which airlines have at least 10 flights?",
    )
    assert "projection_extra_count" in _codes(
        "SELECT Airline, COUNT(*) FROM flights GROUP BY Airline HAVING COUNT(*) >= 10",
        "Which airlines have at least 10 flights?",
    )
    assert "projection_extra_count" not in _codes(
        "SELECT Airline FROM flights GROUP BY Airline HAVING COUNT(*) >= 10",
        "Which airlines have at least 10 flights?",
    )


def test_distinct_required_is_flagged_when_missing() -> None:
    assert _codes(
        "SELECT Country FROM singer WHERE Age > 20",
        "What are all distinct countries where singers above age 20 are from?",
    ) == {"distinct_missing"}


# ============================================================
# Projection duplicate alias detection
# ============================================================

def test_duplicate_alias_detected() -> None:
    """Same column with two different aliases → projection_duplicate_alias."""
    codes = _codes(
        "SELECT a.Airline AS airline, a.Airline AS airlines_airline FROM airlines AS a",
        "Find all airlines that have at least 10 flights.",
    )
    assert "projection_duplicate_alias" in codes


def test_duplicate_alias_airport_name() -> None:
    """AirportName AS name + AirportName AS airports_airportname."""
    codes = _codes(
        "SELECT AirportName AS name, AirportName AS airports_airportname FROM airports",
        "Find the name of airports which do not have any flight in and out.",
    )
    assert "projection_duplicate_alias" in codes


def test_no_duplicate_alias_for_different_columns() -> None:
    """Different columns should NOT trigger duplicate alias."""
    codes = _codes(
        "SELECT PetType, AVG(pet_age) FROM pets GROUP BY PetType",
        "Find the average age for each type of pet.",
    )
    assert "projection_duplicate_alias" not in codes


def test_select_star_triggers_extra_columns() -> None:
    """SELECT many entity columns when question asks for one ID."""
    codes = _codes(
        "SELECT student.StuID, student.LName, student.Fname, student.Age FROM student JOIN has_pet ON student.StuID = has_pet.StuID WHERE student.LName = 'Smith'",
        "Find the id of the pet owned by student whose last name is Smith.",
    )
    assert "projection_extra_columns" in codes
