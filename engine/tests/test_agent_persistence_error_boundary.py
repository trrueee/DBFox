from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from engine.app.safe_errors import FixedErrorCode
from engine.agent_core.types import AgentRunRequest, AgentRunResponse, AgentRuntimeEvent


def _isolated_capture_logger(caplog, name: str) -> logging.Logger:
    logger = logging.Logger(name)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    return logger


def test_runtime_event_persistence_failure_logs_only_type(monkeypatch, caplog) -> None:
    import engine.agent_core.persistence.events as events_module

    sentinel = "runtime-event-persistence-secret-sentinel"

    class FailingDb:
        def add(self, _record) -> None:
            pass

        def flush(self) -> None:
            raise RuntimeError(f"provider authorization={sentinel}")

    logger = _isolated_capture_logger(caplog, "test.runtime_event_persistence")
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(events_module, "logger", logger)
            with pytest.raises(RuntimeError):
                events_module.record_runtime_event(
                    FailingDb(),
                    "session-persistence-boundary",
                    AgentRuntimeEvent(
                        event_id="event-persistence-boundary",
                        run_id="run-persistence-boundary",
                        sequence=1,
                        created_at_ms=1,
                        type="agent.progress.update",
                    ),
                )
    finally:
        logger.removeHandler(caplog.handler)

    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_persistence_runtime_event" in caplog.text


def test_complete_run_persistence_failure_logs_only_type(monkeypatch, caplog) -> None:
    import engine.agent_core.persistence.runs as runs_module

    sentinel = "complete-run-persistence-secret-sentinel"
    run = SimpleNamespace(assistant_message_id=None)

    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            return run

    class FailingDb:
        def query(self, _model):
            return Query()

        def get(self, _model, _identity):
            return None

        def flush(self) -> None:
            raise RuntimeError(f"database password={sentinel}")

    logger = _isolated_capture_logger(caplog, "test.complete_run_persistence")
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(runs_module, "logger", logger)
            with pytest.raises(RuntimeError):
                runs_module.complete_run(
                    FailingDb(),
                    AgentRunResponse(
                        run_id="run-persistence-boundary",
                        session_id="session-persistence-boundary",
                        success=True,
                        status="completed",
                        question="q",
                    ),
                )
    finally:
        logger.removeHandler(caplog.handler)

    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_persistence_complete_run" in caplog.text


def test_persistence_coordinator_failure_logs_only_type(monkeypatch, caplog) -> None:
    import engine.agent.app.persistence_coordinator as coordinator_module

    sentinel = "coordinator-persistence-secret-sentinel"

    class FailingStore:
        def start_run(self, *_args, **_kwargs) -> None:
            raise RuntimeError(f"vault token={sentinel}")

    class Db:
        def rollback(self) -> None:
            pass

    logger = _isolated_capture_logger(caplog, "test.persistence_coordinator")
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(coordinator_module, "logger", logger)
            coordinator = coordinator_module.AgentPersistenceCoordinator(
                Db(),
                FailingStore(),
                object(),
                enabled=True,
            )
            coordinator.start_run(
                AgentRunRequest(datasource_id="ds-persistence", question="q"),
                run_id="run-persistence-boundary",
                session_id="session-persistence-boundary",
            )
    finally:
        logger.removeHandler(caplog.handler)

    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_persistence_start" in caplog.text


def test_failed_run_persistence_discards_a_caller_supplied_error_message() -> None:
    import engine.agent_core.persistence.runs as runs_module

    sentinel = "failed-run-persistence-secret-sentinel"
    run = SimpleNamespace(assistant_message_id=None)

    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            return run

    class Db:
        def query(self, _model):
            return Query()

        def get(self, _model, _identity):
            return None

        def flush(self) -> None:
            pass

    response = AgentRunResponse(
        run_id="run-persistence-boundary",
        session_id="session-persistence-boundary",
        success=False,
        status="failed",
        question="q",
        error=sentinel,
    )

    runs_module.complete_run(Db(), response)
    runs_module.fail_run(
        Db(),
        response.run_id,
        response.session_id,
        FixedErrorCode.AGENT_RUNTIME_ERROR,
        response,
    )

    assert run.error == "The agent run could not be completed."
    assert run.error_message == "The agent run could not be completed."
    assert sentinel not in run.response_json
