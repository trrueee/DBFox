from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from verification.bench.core.authority.runtime import _run_case
from verification.bench.core.authority.schema import AuthorityCase


def test_core_authority_bench_rejects_an_unfrozen_resource(db_session) -> None:
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    case = AuthorityCase.model_validate(
        {
            "case_id": "unauthorized-resource",
            "authorized_ids": ["alpha"],
            "requested_id": "beta",
            "expect_access": False,
        }
    )

    outcome = _run_case(
        factory,
        suite_id="core.authority.scripted",
        case=case,
        repetition=1,
    )

    assert outcome.verdict == "pass"
    assert outcome.metrics["authority.selection_accuracy"] == 1.0
    assert outcome.metrics["authority.violation_count"] == 0.0
    assert outcome.evidence["access_log"] == ()
