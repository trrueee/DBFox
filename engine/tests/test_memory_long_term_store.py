from __future__ import annotations

from datetime import datetime, timedelta, timezone

from engine.memory.long_term_store import SQLiteLongTermMemoryStore


def test_sqlite_long_term_memory_store_persists_records_across_instances(tmp_path):
    db_path = tmp_path / "memory.sqlite"
    first = SQLiteLongTermMemoryStore(db_path)

    written = first.upsert(
        namespace=("user", "u1", "project", "p1"),
        key="pref-language",
        type="user_preference",
        text="Answer in Chinese.",
        content={"preference_type": "language", "value": "zh-CN"},
        source="user_explicit",
        user_id="u1",
        project_id="p1",
    )

    second = SQLiteLongTermMemoryStore(db_path)
    loaded = second.get(written.id)

    assert loaded is not None
    assert loaded.id == "pref-language"
    assert loaded.namespace == ("user", "u1", "project", "p1")
    assert loaded.text == "Answer in Chinese."
    assert loaded.content["value"] == "zh-CN"
    assert second.count() == 1


def test_sqlite_long_term_memory_store_matches_search_contract(tmp_path):
    db_path = tmp_path / "memory.sqlite"
    store = SQLiteLongTermMemoryStore(db_path)
    expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    active = store.upsert(
        namespace=("user", "u1", "project", "p1"),
        key="metric-rule",
        type="project_rule",
        text="Use net revenue as the metric.",
        confidence=0.95,
        project_id="p1",
        user_id="u1",
    )
    store.upsert(
        namespace=("user", "u1", "project", "p1"),
        key="low-confidence-rule",
        type="project_rule",
        text="Use gross revenue as the metric.",
        confidence=0.4,
        project_id="p1",
        user_id="u1",
    )
    store.upsert(
        namespace=("user", "u1", "project", "p1"),
        key="expired-rule",
        type="project_rule",
        text="Expired metric memory.",
        confidence=1.0,
        project_id="p1",
        user_id="u1",
        expires_at=expired_at,
    )
    deleted = store.upsert(
        namespace=("user", "u1", "project", "p1"),
        key="deleted-rule",
        type="project_rule",
        text="Deleted metric memory.",
        confidence=1.0,
        project_id="p1",
        user_id="u1",
    )
    store.delete(deleted.id)
    store.upsert(
        namespace=("user", "u2", "project", "p1"),
        key="other-user-rule",
        type="project_rule",
        text="Other user metric memory.",
        confidence=1.0,
        project_id="p1",
        user_id="u2",
    )

    results = store.search(
        namespaces=[("user", "u1")],
        types=["project_rule"],
        keywords=["metric"],
        min_confidence=0.8,
        limit=10,
    )

    assert [record.id for record in results] == [active.id]
    assert store.get(deleted.id) is None
