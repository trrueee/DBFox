"""Submission/acknowledgement lifetime independent of the browser platform."""
import asyncio

import pytest

from engine.computer.browser import OwnedBrowser
from engine.computer.contracts import ComputerError


def test_browser_submission_enters_the_operation_before_leaving_the_fence(tmp_path):
    browser = OwnedBrowser(tmp_path)
    release = asyncio.Event()
    events = []
    fenced = True

    async def operation():
        assert fenced
        events.append("submitted")
        await release.wait()
        assert not fenced
        events.append("completed")

    async def allow_completion():
        release.set()

    prepared = browser._prepared(operation)
    try:
        prepared.dispatch()
        fenced = False
        assert events == ["submitted"]
        browser._run(allow_completion())
        assert prepared.wait is not None
        prepared.wait()
        assert events == ["submitted", "completed"]
        prepared.wait()
        assert events == ["submitted", "completed"]
    finally:
        browser.close()


def test_submitted_browser_action_is_never_enqueued_twice(tmp_path):
    browser = OwnedBrowser(tmp_path)
    attempts = []

    async def operation():
        attempts.append("sent")

    prepared = browser._prepared(operation)
    try:
        prepared.dispatch()
        with pytest.raises(ComputerError) as failure:
            prepared.dispatch()
        assert failure.value.code == "COMPUTER_INVOCATION_DUPLICATE"
        assert prepared.wait is not None
        prepared.wait()
        assert attempts == ["sent"]
    finally:
        browser.close()


def test_eager_failure_is_received_by_the_waiter(tmp_path):
    browser = OwnedBrowser(tmp_path)

    async def operation():
        raise ComputerError("COMPUTER_ACTION_CANCELLED", "Cancelled before input.")

    prepared = browser._prepared(operation)
    try:
        prepared.dispatch()
        assert prepared.wait is not None
        with pytest.raises(ComputerError) as failure:
            prepared.wait()
        assert failure.value.code == "COMPUTER_ACTION_CANCELLED"
    finally:
        browser.close()
