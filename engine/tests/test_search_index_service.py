from __future__ import annotations

from engine.crypto import encrypt_password
from engine.models import DEFAULT_PROJECT_ID, DataSource, QueryHistory
from engine.persistence.search_index import SearchIndexService


def _datasource(db_session, datasource_id: str) -> DataSource:
    cipher, nonce = encrypt_password("secret")
    ds = DataSource(
        id=datasource_id,
        project_id=DEFAULT_PROJECT_ID,
        name=datasource_id,
        host="127.0.0.1",
        port=0,
        database_name=":memory:",
        username="readonly",
        password_ciphertext=cipher,
        password_nonce=nonce,
        db_type="sqlite",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


def _history(db_session, history_id: str, datasource_id: str, question: str, sql: str) -> QueryHistory:
    item = QueryHistory(
        id=history_id,
        data_source_id=datasource_id,
        question=question,
        submitted_sql=sql,
        generated_sql=sql,
        safe_sql=sql,
        executed_sql=sql,
        guardrail_result="pass",
        guardrail_checks="[]",
        execution_status="success",
    )
    db_session.add(item)
    db_session.commit()
    return item


def test_query_history_index_search_and_delete(db_session) -> None:
    _datasource(db_session, "ds-search")
    history = _history(db_session, "hist-1", "ds-search", "find revenue", "SELECT revenue FROM orders")
    service = SearchIndexService(db_session)

    service.ensure_schema()
    service.index_query_history(history)
    db_session.commit()

    assert service.search_query_history("revenue", datasource_id="ds-search", limit=10) == ["hist-1"]

    service.delete_query_history("hist-1")
    db_session.commit()

    assert service.search_query_history("revenue", datasource_id="ds-search", limit=10) == []


def test_query_history_index_clear_is_datasource_scoped(db_session) -> None:
    _datasource(db_session, "ds-a")
    _datasource(db_session, "ds-b")
    hist_a = _history(db_session, "hist-a", "ds-a", "customer churn", "SELECT churn FROM customers")
    hist_b = _history(db_session, "hist-b", "ds-b", "customer churn", "SELECT churn FROM customers")
    service = SearchIndexService(db_session)
    service.ensure_schema()
    service.index_query_history(hist_a)
    service.index_query_history(hist_b)
    db_session.commit()

    service.clear_query_history("ds-a")
    db_session.commit()

    assert service.search_query_history("churn", datasource_id="ds-a", limit=10) == []
    assert service.search_query_history("churn", datasource_id="ds-b", limit=10) == ["hist-b"]


def test_rebuild_query_history_index_backfills_existing_history(db_session) -> None:
    _datasource(db_session, "ds-rebuild")
    _history(db_session, "hist-rebuild", "ds-rebuild", "gross margin", "SELECT margin FROM finance")
    service = SearchIndexService(db_session)

    service.ensure_schema()
    service.rebuild_query_history_index()
    db_session.commit()

    assert service.search_query_history("margin", datasource_id="ds-rebuild", limit=10) == ["hist-rebuild"]
