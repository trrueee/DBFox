import pytest

from engine.agent.events import LiveStreamGap, LiveStreamHub
from engine.agent.run_item import RunItemDelta, RunItemType


def _delta(revision: int, content: str = "x", *, offset: int | None = None) -> RunItemDelta:
    return RunItemDelta(
        session_id="session", run_id="run", turn_id="turn",
        item_id="message:run:turn", item_type=RunItemType.MESSAGE,
        field="content", revision=revision,
        offset=revision - 1 if offset is None else offset,
        content=content,
    )


def test_live_stream_pushes_without_polling_and_deduplicates_offsets():
    hub = LiveStreamHub()
    with hub.subscribe("run") as subscription:
        assert hub.publish(_delta(1, "首")) is True
        assert subscription.receive(timeout=0.01).content == "首"
        assert hub.publish(_delta(1, "重复")) is False
        assert subscription.receive(timeout=0.01) is None


def test_live_stream_rejects_offset_gap():
    hub = LiveStreamHub()
    with pytest.raises(LiveStreamGap):
        hub.publish(_delta(2))


def test_session_subscription_receives_deltas_for_new_runs():
    hub = LiveStreamHub()
    subscription = hub.subscribe_session("session")
    hub.publish(_delta(1, "live"))
    assert subscription.receive(timeout=0.01).content == "live"
    subscription.close()


def test_late_subscription_receives_full_channel_rebase_then_new_deltas():
    hub = LiveStreamHub()
    hub.publish(_delta(1, "A", offset=0))
    hub.publish(_delta(2, "B", offset=1))

    subscription = hub.subscribe_session("session")
    rebase = subscription.receive(timeout=0.01)
    assert rebase is not None
    assert rebase.offset == 0
    assert rebase.revision == 2
    assert rebase.content == "AB"

    hub.publish(_delta(3, "C", offset=2))
    appended = subscription.receive(timeout=0.01)
    assert appended is not None
    assert appended.offset == 2
    assert appended.revision == 3
    assert appended.content == "C"
    subscription.close()
