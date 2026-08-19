"""Capability DLC P0 characterization of the pre-migration runtime boundary.

P1 replaces the former parent/worker registrar duplication with one product
composition root. RemoteJob remains in-process-only, so exposing its frozen
tool definitions to the isolated worker does not change model materialization
or select a different execution backend.
"""

from __future__ import annotations

from engine.runtime_composition import build_product_tool_registry


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
    "github_list_files",
    "github_read_file",
    "github_repo_overview",
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
