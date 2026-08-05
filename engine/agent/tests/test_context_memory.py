from __future__ import annotations

import json

from engine.agent.context import ContextAssembler
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentRun, AgentSession, AgentSessionMemory


def test_context_omits_memory_from_an_older_datasource_generation(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-memory-generation"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Memory generation",
        )
    )
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=2,
        content="现在有多少订单？",
        idempotency_key="memory-generation",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.add(
        AgentSessionMemory(
            id="memory-generation",
            session_id=session_id,
            datasource_id=str(test_datasource.id),
            memory_json=json.dumps(
                {
                    "version": 1,
                    "datasource_generation": 1,
                    "recent_runs": [
                        {
                            "run_id": "old-run",
                            "question": "旧问题",
                            "answer_summary": "旧答案",
                            "datasource_generation": 1,
                        }
                    ],
                    "working_set": {
                        "datasource_generation": 1,
                        "referenced_artifact_ids": ["artifact-stale"],
                    },
                    "stable_context": {
                        "database_name": "old_database",
                        "verified_claims": [
                            {
                                "claim": "旧数据共有 42 行",
                                "datasource_generation": 1,
                            }
                        ],
                    },
                }
            ),
        )
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(admission.run_id)

    assert db_session.get(AgentRun, admission.run_id).datasource_generation == 2
    assert snapshot.session_memory["datasource_generation"] == 2
    assert snapshot.session_memory["working_set"] == {}
    assert snapshot.session_memory["stable_context"]["evidence_references"] == []
    assert "verified_claims" not in snapshot.session_memory["stable_context"]
    assert "old_database" not in snapshot.session_memory["stable_context"]
    assert "recent_runs" not in snapshot.session_memory
    assert "conversation_summary" not in snapshot.session_memory
    assert snapshot.session_memory["freshness"] == {
        "omitted_stale_runs": 1,
        "omitted_stale_evidence_references": 0,
        "omitted_legacy_verified_claims": 1,
    }
