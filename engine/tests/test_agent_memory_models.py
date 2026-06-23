from __future__ import annotations

from engine.agent_core.memory import (
    normalize_sql_for_fingerprint,
    sql_fingerprint,
    upsert_memory_ref,
)
from engine.agent_core.persistence.memory import (
    list_reusable_sqls,
    load_session_memory,
    save_session_memory,
    upsert_reusable_sql,
)
from engine.models import AgentSessionMemory, DataSource, ReusableSQL


def test_sql_fingerprint_ignores_whitespace_and_case() -> None:
    left = "SELECT  id, name  FROM users WHERE deleted_at IS NULL"
    right = " select id, name from users where deleted_at is null "

    assert normalize_sql_for_fingerprint(left) == normalize_sql_for_fingerprint(right)
    assert sql_fingerprint(left) == sql_fingerprint(right)


def test_upsert_memory_ref_updates_existing_ref_by_datasource_and_fingerprint() -> None:
    refs = [
        {
            "id": "mem_old",
            "kind": "result_view_ref",
            "datasource_id": "ds_1",
            "sql_fingerprint": "fp_1",
            "usage_count": 1,
            "last_used_at": "2026-06-20T00:00:00Z",
        }
    ]

    updated = upsert_memory_ref(
        refs,
        {
            "id": "mem_new",
            "kind": "result_view_ref",
            "datasource_id": "ds_1",
            "sql_fingerprint": "fp_1",
            "safe_sql": "SELECT 1",
            "columns": ["count"],
            "last_used_at": "2026-06-23T00:00:00Z",
        },
        max_refs=10,
    )

    assert len(updated) == 1
    assert updated[0]["id"] == "mem_old"
    assert updated[0]["safe_sql"] == "SELECT 1"
    assert updated[0]["usage_count"] == 2
    assert updated[0]["last_used_at"] == "2026-06-23T00:00:00Z"


def _datasource(datasource_id: str = "ds_memory") -> DataSource:
    return DataSource(
        id=datasource_id,
        name="Memory DS",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        status="active",
    )


def test_save_session_memory_upserts_conversation_level_payload(db_session) -> None:
    db_session.add(_datasource())
    db_session.commit()

    first = save_session_memory(
        db_session,
        session_id="session_memory_1",
        datasource_id="ds_memory",
        payload={
            "conversation_summary": "用户在分析注册趋势。",
            "sql_ref_index": [{"safe_sql": "SELECT COUNT(*) FROM users"}],
        },
    )
    second = save_session_memory(
        db_session,
        session_id="session_memory_1",
        datasource_id="ds_memory",
        payload={
            "conversation_summary": "用户在分析注册趋势，后来继续追问留存。",
            "artifact_ref_index": [{"artifact_id": "result_view_1"}],
        },
    )
    loaded = load_session_memory(db_session, "session_memory_1")

    rows = db_session.query(AgentSessionMemory).all()
    assert len(rows) == 1
    assert first.id == second.id
    assert loaded is not None
    assert loaded["conversation_summary"] == "用户在分析注册趋势，后来继续追问留存。"
    assert loaded["artifact_ref_index"] == [{"artifact_id": "result_view_1"}]


def test_upsert_reusable_sql_updates_by_datasource_and_fingerprint(db_session) -> None:
    db_session.add(_datasource())
    db_session.commit()

    first = upsert_reusable_sql(
        db_session,
        datasource_id="ds_memory",
        question="统计用户数",
        safe_sql="SELECT COUNT(*) AS total_users FROM users",
        purpose="count users",
        involved_tables=["users"],
        result_columns=["total_users"],
        verified=True,
    )
    second = upsert_reusable_sql(
        db_session,
        datasource_id="ds_memory",
        question="再统计一下用户数",
        safe_sql=" select count(*) as total_users from users ",
        purpose="reuse count users",
        involved_tables=["users"],
        result_columns=["total_users"],
        verified=True,
    )

    rows = db_session.query(ReusableSQL).all()
    assert len(rows) == 1
    assert first.id == second.id
    assert second.question == "再统计一下用户数"
    assert second.usage_count == 2
    assert second.verified is True
    assert second.sql_fingerprint == sql_fingerprint("SELECT COUNT(*) AS total_users FROM users")


def test_list_reusable_sqls_returns_verified_sql_for_datasource_only(db_session) -> None:
    db_session.add_all([_datasource("ds_memory"), _datasource("ds_other")])
    db_session.commit()

    verified = upsert_reusable_sql(
        db_session,
        datasource_id="ds_memory",
        question="统计用户数",
        safe_sql="SELECT COUNT(*) AS total_users FROM users",
        purpose="count users",
        involved_tables=["users"],
        result_columns=["total_users"],
        verified=True,
    )
    upsert_reusable_sql(
        db_session,
        datasource_id="ds_memory",
        question="未验证查询",
        safe_sql="SELECT * FROM risky_table",
        verified=False,
    )
    upsert_reusable_sql(
        db_session,
        datasource_id="ds_other",
        question="其他数据源用户数",
        safe_sql="SELECT COUNT(*) AS total_users FROM users",
        verified=True,
    )
    db_session.commit()

    candidates = list_reusable_sqls(db_session, datasource_id="ds_memory", limit=5)

    assert [candidate["id"] for candidate in candidates] == [verified.id]
    assert candidates[0]["safe_sql"] == "SELECT COUNT(*) AS total_users FROM users"
    assert candidates[0]["sql_fingerprint"] == sql_fingerprint("SELECT COUNT(*) AS total_users FROM users")
    assert candidates[0]["tables"] == ["users"]
    assert candidates[0]["columns"] == ["total_users"]
