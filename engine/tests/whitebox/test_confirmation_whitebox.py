import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.db import Base
from engine.models import ConfirmationToken
from engine.policy.confirmation import ConfirmationManager


def _create_token(manager: ConfirmationManager, db_session) -> str:
    return manager.create_confirmation(
        db=db_session,
        datasource_id="ds-1",
        action="query",
        details={"sql": "SELECT 1"},
        expected_confirm_text="confirm",
    )


def _validate(manager: ConfirmationManager, db_session, token: str, **overrides):
    values = {
        "db": db_session,
        "token": token,
        "confirm_text": "confirm",
        "expected_action": "query",
        "expected_datasource_id": "ds-1",
        "expected_details": {"sql": "SELECT 1"},
    }
    values.update(overrides)
    return manager.validate_and_consume(**values)


def test_conf1_not_exists(db_session):
    ok, msg = _validate(ConfirmationManager(), db_session, "invalid-token")
    assert not ok
    assert "无效或已过期" in msg


def test_conf2_expired(db_session):
    manager = ConfirmationManager(ttl_seconds=-1)
    token = _create_token(manager, db_session)
    ok, msg = _validate(manager, db_session, token)
    assert not ok
    assert "已过期" in msg
    assert db_session.get(ConfirmationToken, token) is None


def test_conf3_action_mismatch_does_not_consume_token(db_session):
    manager = ConfirmationManager()
    token = _create_token(manager, db_session)
    ok, msg = _validate(manager, db_session, token, expected_action="other_action")
    assert not ok
    assert "操作类型不匹配" in msg

    ok, msg = _validate(manager, db_session, token)
    assert ok
    assert msg == ""


def test_conf4_datasource_mismatch(db_session):
    manager = ConfirmationManager()
    token = _create_token(manager, db_session)
    ok, msg = _validate(manager, db_session, token, expected_datasource_id="ds-other")
    assert not ok
    assert "数据源不匹配" in msg


def test_conf5_details_mismatch(db_session):
    manager = ConfirmationManager()
    token = _create_token(manager, db_session)
    ok, msg = _validate(manager, db_session, token, expected_details={"sql": "SELECT 2"})
    assert not ok
    assert "参数" in msg and "不匹配" in msg


def test_conf6_text_mismatch(db_session):
    manager = ConfirmationManager()
    token = _create_token(manager, db_session)
    ok, msg = _validate(manager, db_session, token, confirm_text="wrong_confirm")
    assert not ok
    assert "文本不匹配" in msg


def test_conf7_success_is_durable_across_manager_instances(db_session):
    token = _create_token(ConfirmationManager(), db_session)
    assert db_session.get(ConfirmationToken, token) is not None

    ok, msg = _validate(ConfirmationManager(), db_session, token)
    assert ok
    assert msg == ""
    assert db_session.get(ConfirmationToken, token) is None


def test_conf8_double_consume(db_session):
    manager = ConfirmationManager()
    token = _create_token(manager, db_session)
    ok1, _ = _validate(manager, db_session, token)
    assert ok1
    ok2, msg2 = _validate(manager, db_session, token)
    assert not ok2
    assert "无效或已过期" in msg2


def test_conf9_concurrent_successful_consumption_is_atomic(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'confirmation.db').as_posix()}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    manager = ConfirmationManager()
    try:
        with SessionLocal() as setup_session:
            token = _create_token(manager, setup_session)

        barrier = threading.Barrier(2)
        results: list[bool] = []
        result_lock = threading.Lock()

        def attempt() -> None:
            with SessionLocal() as session:
                barrier.wait()
                ok, _ = _validate(manager, session, token)
                with result_lock:
                    results.append(ok)

        first = threading.Thread(target=attempt)
        second = threading.Thread(target=attempt)
        first.start()
        second.start()
        first.join()
        second.join()

        assert results.count(True) == 1
        assert results.count(False) == 1
    finally:
        engine.dispose()
