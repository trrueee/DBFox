"""Action runs keep the same durable lease contract as Agent runs."""
import time

import pytest
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import BaseTool, ToolInputModel, ToolOutputModel, ToolExecutionSpec, ToolPolicy, ToolPresentation
from engine.dlc import action_runs
from engine.dlc.snapshot import RuntimeContributionSnapshot
from engine.agent.run import SessionLeaseConflict
from engine.models import AgentRun, AgentSession, Project
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver


class ReadInput(ToolInputModel):
    pass


class ReadOutput(ToolOutputModel):
    observed: bool


class DelayedRead(BaseTool[ReadInput, ReadOutput]):
    name = "controlled_read"
    group = "lifecycle_test"
    description = "Read a controlled boundary."
    input_model, output_model = ReadInput, ReadOutput
    execution = ToolExecutionSpec(recovery="retry_safe", timeout_seconds=10)
    policy = ToolPolicy(risk_level="safe")
    presentation = ToolPresentation(title="Synthetic read", category="explore")

    def run(self, tool_input, context):
        time.sleep(3.2)
        return ReadOutput(observed=True)


@pytest.fixture
def action(db_session, monkeypatch):
    monkeypatch.setattr(action_runs, "_ACTION_LEASE_TTL_SECONDS", 3)
    db_session.add(Project(id="action-project", name="synthetic"))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    registry = ToolRegistry()
    registry.register(DelayedRead(), owner="dbfox.review", package_digest="0" * 64)
    snapshot = RuntimeContributionSnapshot(snapshot_id="synthetic", active_dlcs=(), tools=(), resource_providers=(),
        resource_resolvers=(), context_contributors=(), completion_constraints=(), completion_supports=(),
        artifact_contracts=(), operations=())
    host = action_runs.DlcActionRunsHostImpl(dlc_id="dbfox.review", project_id="action-project", snapshot=snapshot,
        session_factory=factory, registry=registry, resource_resolver=CompositeResourceResolver(),
        resource_authorizer=lambda db, project, refs: ())
    value = host.start(title="synthetic", question="read", requested_resources=())
    yield value, factory
    value._close_resources()


def test_action_renews_through_a_tool_longer_than_its_lease(action):
    value, factory = action
    with value:
        assert value.invoke("controlled_read", {}).status == "success"
        value.complete(summary="done")
    with factory() as db:
        assert db.get(AgentRun, value.run_id).status == "completed"
        assert db.get(AgentSession, value.session_id).lease_owner is None
    assert not value._heartbeat.is_alive()


@pytest.mark.parametrize("original_error", [False, True])
def test_stolen_lease_closes_resources_without_overwriting_owner(action, original_error, monkeypatch):
    value, factory = action
    closed = []
    close = value._executor.close
    monkeypatch.setattr(value._executor, "close", lambda **kwargs: (closed.append(True), close(**kwargs)))
    with factory() as db:
        session = db.get(AgentSession, value.session_id)
        session.lease_owner = "new-owner"
        session.lease_token += 1
        db.commit()
    error = ValueError("original error") if original_error else None
    if original_error:
        assert value.__exit__(ValueError, error, None) is False
    else:
        with pytest.raises(SessionLeaseConflict):
            value.__exit__(None, None, None)
    assert closed
    assert not value._heartbeat.is_alive()
    with factory() as db:
        assert db.get(AgentSession, value.session_id).lease_owner == "new-owner"
