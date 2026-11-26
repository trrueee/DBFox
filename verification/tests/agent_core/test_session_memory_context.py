"""Session memory is injected as a bounded, Core-owned prompt envelope."""

from __future__ import annotations

import json

from engine.agent.context import ContextAssembler
from engine.models import AgentSession, AgentSessionMemory


def _session(db_session, *, memory: object | None = None) -> AgentSession:
    session = AgentSession(id="session_memory", title="Memory")
    db_session.add(session)
    if memory is not None:
        db_session.add(
            AgentSessionMemory(
                session_id="session_memory",
                memory_json=(
                    memory if isinstance(memory, str) else json.dumps(memory)
                ),
            )
        )
    db_session.commit()
    return session


def test_core_working_set_and_evidence_are_projected(db_session) -> None:
    session = _session(
        db_session,
        memory={
            "version": 1,
            "working_set": {
                "selected_artifact_id": "artifact_selected",
                "referenced_artifact_ids": ["artifact_a", "artifact_b"],
                "open_questions": ["Which region should we compare?"],
            },
            "stable_context": {
                "evidence_references": [
                    {
                        "evidence_id": "evidence_1",
                        "artifact_id": "artifact_a",
                        "observed_at": "2026-11-24T00:00:00+00:00",
                        "run_id": "run_previous",
                    }
                ],
                "capability_private_state": {"rows": [1, 2, 3]},
            },
        },
    )
    sources: list[object] = []

    projected = ContextAssembler(db_session)._session_memory(session, sources)

    assert projected["version"] == 1
    assert projected["working_set"] == {
        "selected_artifact_id": "artifact_selected",
        "referenced_artifact_ids": ["artifact_a", "artifact_b"],
        "open_questions": ["Which region should we compare?"],
    }
    assert projected["evidence_references"] == [
        {
            "artifact_id": "artifact_a",
            "observed_at": "2026-11-24T00:00:00+00:00",
        }
    ]
    assert "stable_context" not in projected
    assert "capability_private_state" not in json.dumps(projected)
    assert sources[-1].included is True


def test_missing_memory_produces_no_envelope(db_session) -> None:
    session = _session(db_session)
    sources: list[object] = []

    projected = ContextAssembler(db_session)._session_memory(session, sources)

    assert projected == {}
    assert sources[-1].included is False


def test_corrupt_memory_is_ignored(db_session) -> None:
    session = _session(db_session, memory="{not-json")
    sources: list[object] = []

    projected = ContextAssembler(db_session)._session_memory(session, sources)

    assert projected == {}
    assert sources[-1].included is False


def test_oversized_memory_is_trimmed_to_the_prompt_envelope(db_session) -> None:
    session = _session(
        db_session,
        memory={
            "version": 1,
            "working_set": {
                "referenced_artifact_ids": [
                    f"artifact_{index}_" + "x" * 400 for index in range(8)
                ],
                "open_questions": ["q" * 200 for _ in range(5)],
            },
            "stable_context": {
                "evidence_references": [
                    {
                        "artifact_id": f"artifact_{index}_" + "y" * 400,
                        "observed_at": "2026-11-24T00:00:00+00:00",
                    }
                    for index in range(8)
                ]
            },
        },
    )
    sources: list[object] = []

    projected = ContextAssembler(db_session)._session_memory(session, sources)

    assert projected
    assert len(json.dumps(projected, ensure_ascii=False).encode("utf-8")) <= 4_096
    assert len(projected["working_set"]["referenced_artifact_ids"]) <= 2
    assert len(projected["working_set"]["open_questions"]) <= 2
    assert len(projected["evidence_references"]) <= 2


def test_legacy_field_types_cannot_break_the_context_build(db_session) -> None:
    session = _session(db_session, memory={
        "version": 1,
        "working_set": {
            "selected_artifact_id": "artifact_selected",
            "open_questions": 42,
            "referenced_artifact_ids": "artifact_string",
        },
        "stable_context": {"evidence_references": True},
    })

    projected = ContextAssembler(db_session)._session_memory(session, [])

    assert projected["working_set"] == {
        "selected_artifact_id": "artifact_selected",
        "open_questions": [],
        "referenced_artifact_ids": [],
    }
    assert "evidence_references" not in projected
