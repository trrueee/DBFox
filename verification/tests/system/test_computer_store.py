"""Durable sharing authority, independent of OS automation and model decisions."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import sys

import pytest
from sqlalchemy.orm import sessionmaker

from engine.computer.contracts import ComputerError, GrantStatus, TARGET_KIND, TargetIdentity
from engine.computer.store import ComputerGrantStore
from engine.models import AgentSession, Project
from engine.resource import ResourceScopeRef
from verification.support.metadata import create_migrated_metadata_engine


@pytest.fixture
def grants(tmp_path: Path) -> Iterator[tuple[ComputerGrantStore, list[int]]]:
    engine = create_migrated_metadata_engine(tmp_path / "computer.sqlite")
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        db.add(Project(id="p", name="Computer verification"))
        db.flush()
        db.add_all((AgentSession(id="s", project_id="p"), AgentSession(id="other", project_id="p")))
    clock = [1_000_000]
    yield ComputerGrantStore(sessions, clock=lambda: clock[0]), clock
    engine.dispose()


def _target() -> TargetIdentity:
    return TargetIdentity(kind="window", title="Private fixture", executable=sys.executable,
                          process_id=123, process_started_at=100, window_handle="1abc")


def _ref(grant) -> ResourceScopeRef:
    return ResourceScopeRef(kind=TARGET_KIND, id=grant.id, version=grant.version)


def test_observation_authority_cannot_dispatch_input(grants) -> None:
    store, _ = grants
    grant = store.create("s", _target(), permission="observe", duration_minutes=5)
    assert store.require("s", _ref(grant)).id == grant.id
    dispatched = []
    with pytest.raises(ComputerError) as failure:
        with store.effect_lease("s", _ref(grant), lambda: False):
            dispatched.append("input")
    assert failure.value.code == "COMPUTER_OBSERVE_ONLY"
    assert dispatched == []


def test_replacement_never_reauthorizes_the_old_target_reference(grants) -> None:
    store, _ = grants
    old = store.create("s", _target(), permission="control", duration_minutes=15)
    with pytest.raises(ComputerError, match="已共享"):
        store.create("s", _target(), permission="control", duration_minutes=15)
    new = store.create("s", _target(), permission="control", duration_minutes=15, replace_existing=True)
    assert new.id != old.id and new.version != old.version
    with pytest.raises(ComputerError, match="已暂停、结束或到期"):
        with store.effect_lease("s", _ref(old), lambda: False):
            pytest.fail("An old sharing reference reached input dispatch")
    assert store.require("s", _ref(new), control=True).id == new.id


def test_stop_and_expiry_prevent_the_effect_at_its_boundary(grants) -> None:
    store, clock = grants
    grant = store.create("s", _target(), permission="control", duration_minutes=5)
    assert store.stop("s") == (grant.id,)
    assert store.get("s", grant.id).status == GrantStatus.PAUSED
    assert store.descriptors("s") == ()
    with pytest.raises(ComputerError, match="共享已暂停"):
        store.require("s", _ref(grant), control=True)
    grant = store.create("s", _target(), permission="control", duration_minutes=5, replace_existing=True)
    clock[0] = grant.expires_at
    assert store.get("s", grant.id).status == GrantStatus.EXPIRED
    with pytest.raises(ComputerError, match="共享已暂停"):
        with store.effect_lease("s", _ref(grant), lambda: False):
            pytest.fail("An expired grant reached input dispatch")


def test_invocation_cancellation_and_conversation_scope_are_checked(grants) -> None:
    store, _ = grants
    grant = store.create("s", _target(), permission="control", duration_minutes=5)
    assert store.descriptors("other") == ()
    with pytest.raises(ComputerError) as failure:
        store.require("other", _ref(grant), control=True)
    assert failure.value.status == 404
    with pytest.raises(ComputerError, match="操作已取消"):
        with store.effect_lease("s", _ref(grant), lambda: True):
            pytest.fail("A cancelled invocation reached input dispatch")


def test_restart_interrupts_sharing_without_reopening_or_replaying(grants) -> None:
    store, clock = grants
    grant = store.create("s", _target(), permission="control", duration_minutes=30)
    restarted = ComputerGrantStore(store.sessions, clock=lambda: clock[0])
    assert restarted.get("s", grant.id).status == GrantStatus.INTERRUPTED
    assert restarted.descriptors("s") == ()
    with pytest.raises(ComputerError, match="代次已变化"):
        restarted.require("s", _ref(grant), control=True)


def test_live_share_remains_visible_after_more_than_one_history_page(grants) -> None:
    store, clock = grants
    window = store.create("s", _target(), permission="control", duration_minutes=30)
    browser = TargetIdentity(kind="browser", title="Synthetic browser", executable="msedge.exe", browser_channel="msedge")
    history = []
    for _ in range(20):
        clock[0] += 1
        old = store.create("s", browser, permission="observe", duration_minutes=5, replace_existing=True)
        store.stop_target("s", old.id, revoke=True)
        history.append(old.id)

    assert [resource.id for resource in store.descriptors("s")] == [window.id]
    visible = store.list("s")
    assert window.id in {grant.id for grant in visible}
    assert len(visible) == 17  # All live shares plus the 16 most recent historical rows.
    assert history[0] not in {grant.id for grant in visible}
    assert store.descriptors("other") == ()
    store.stop_target("s", window.id)
    assert store.get("s", window.id).status == GrantStatus.PAUSED
    assert store.descriptors("s") == ()
