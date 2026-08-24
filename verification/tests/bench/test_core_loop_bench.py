from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from verification.bench.core.loop.runtime import _run_case
from verification.bench.core.loop.schema import CoreLoopCase


def test_core_loop_bench_measures_the_real_production_loop_without_a_dlc(
    db_session,
) -> None:
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    case = CoreLoopCase.model_validate(
        {
            "case_id": "real-loop-case",
            "prompt": "Use the verification tool and finish.",
            "steps": [
                {
                    "kind": "tool",
                    "tool_name": "verification_read",
                    "arguments": {"value": "bounded"},
                },
                {"kind": "answer", "content": "verification complete"},
            ],
            "required_answer_terms": ["verification", "complete"],
            "required_tools": ["verification_read"],
            "max_turns": 2,
            "max_tool_calls": 1,
        }
    )

    outcome = _run_case(
        factory,
        suite_id="core.loop.scripted",
        case=case,
        repetition=1,
    )

    assert outcome.verdict == "pass"
    assert outcome.metrics == {
        "task.success_rate": 1.0,
        "runtime.turns": 2.0,
        "runtime.tool_calls": 1.0,
        "runtime.duplicate_tool_calls": 0.0,
    }
    assert outcome.evidence["tool_names"] == ("verification_read",)
