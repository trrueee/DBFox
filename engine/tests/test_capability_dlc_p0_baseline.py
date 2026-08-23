"""Kernel-only characterization of the shared parent/worker composition root."""

from __future__ import annotations

from engine.runtime_composition import build_product_tool_registry


PARENT_TOOL_NAMES = (
    "conversation_read",
    "conversation_search",
    "remote_job_cancel",
    "remote_job_status",
    "remote_job_submit",
    "request_clarification",
    "update_plan",
)

WORKER_TOOL_NAMES = PARENT_TOOL_NAMES


def test_p1_derives_parent_and_worker_from_one_product_composition() -> None:
    """Worker receives all frozen definitions; RemoteJob is still in-process only."""

    parent = build_product_tool_registry()
    worker = build_product_tool_registry()

    assert parent.frozen is True
    assert worker.frozen is True
    assert parent.tool_names() == PARENT_TOOL_NAMES
    assert worker.tool_names() == WORKER_TOOL_NAMES
    assert parent.tool_names() == worker.tool_names()
