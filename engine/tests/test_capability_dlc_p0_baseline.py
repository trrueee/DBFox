"""Capability DLC P0 characterization of the pre-migration runtime boundary.

This deliberately freezes current behavior rather than introducing the P1
composition root.  In particular, the isolated worker omits RemoteJob tools;
that difference is an observed baseline for the later composition migration,
not a behavior change made here.
"""

from __future__ import annotations

from engine.tools.builtin import register_dbfox_tools
from engine.tools.worker import build_worker_registry


PARENT_TOOL_NAMES = (
    "catalog_overview",
    "catalog_refresh",
    "chart_create",
    "conversation_read",
    "conversation_search",
    "data_preview",
    "file_read",
    "file_search",
    "file_write_patch",
    "remote_job_cancel",
    "remote_job_status",
    "remote_job_submit",
    "request_clarification",
    "result_inspect",
    "result_profile",
    "schema_inspect",
    "schema_list",
    "schema_search",
    "sql_execute_readonly",
    "sql_validate",
    "update_plan",
)

WORKER_TOOL_NAMES = tuple(
    name for name in PARENT_TOOL_NAMES if not name.startswith("remote_job_")
)


def test_p0_freezes_parent_and_worker_tool_composition_difference() -> None:
    """P1 must consciously remove this duplicated composition, not erase it silently."""

    parent = register_dbfox_tools()
    worker = build_worker_registry()

    assert parent.frozen is True
    assert worker.frozen is True
    assert parent.tool_names() == PARENT_TOOL_NAMES
    assert worker.tool_names() == WORKER_TOOL_NAMES
    assert set(parent.tool_names()) - set(worker.tool_names()) == {
        "remote_job_cancel",
        "remote_job_status",
        "remote_job_submit",
    }
