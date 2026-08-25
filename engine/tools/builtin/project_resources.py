"""Bounded read-only discovery of resources available in the current Project."""

from __future__ import annotations

from engine.agent.resource_refs import (
    ProjectResourceProvider,
    discover_resources_from_providers,
)
from engine.models import AgentSession
from engine.tools.builtin.contracts import (
    ProjectResourceSearchInput,
    ProjectResourceSearchOutput,
)
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
    ToolRunContext,
)
from engine.tools.runtime.observation import safe_observation_facts


class ProjectResourceSearchTool(
    BaseTool[ProjectResourceSearchInput, ProjectResourceSearchOutput]
):
    """Search discovery metadata without granting any execution authority."""

    name = "project_resource_search"
    group = "resources"
    description = (
        "Search a bounded page of resources that currently exist in this Project. "
        "Use this only when the supplied Project resource directory is truncated or "
        "does not identify the exact resource needed. This function is discovery only: "
        "it does not select, authorize, or mutate a resource. After finding an identity, "
        "call the actual domain function with that resource id."
    )
    input_model = ProjectResourceSearchInput
    output_model = ProjectResourceSearchOutput
    presentation = ToolPresentation(
        title="查找项目资源",
        category="explore",
        visibility="developer",
    )
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=65_536,
        capabilities=("metadata_read",),
        required_resources=(),
    )

    def __init__(self, providers: tuple[ProjectResourceProvider, ...]) -> None:
        self._providers = providers

    def run(
        self,
        tool_input: ProjectResourceSearchInput,
        context: ToolRunContext,
    ) -> ProjectResourceSearchOutput:
        db = context.require_metadata()
        aggregate = db.get(AgentSession, context.require_request().session_id)
        project_id = str(aggregate.project_id or "") if aggregate is not None else ""
        resources = list(
            discover_resources_from_providers(db, project_id, self._providers)
        )
        if tool_input.kinds:
            allowed_kinds = frozenset(tool_input.kinds)
            resources = [item for item in resources if item.kind in allowed_kinds]
        if tool_input.query:
            query = tool_input.query.casefold()
            resources = [
                item
                for item in resources
                if query in item.kind.casefold()
                or query in item.id.casefold()
                or query in item.name.casefold()
            ]
        resources.sort(key=lambda item: (item.kind, item.name.casefold(), item.id))
        offset = int(tool_input.cursor or "0")
        page = resources[offset : offset + tool_input.limit]
        next_offset = offset + len(page)
        has_more = next_offset < len(resources)
        return ProjectResourceSearchOutput(
            resources=page,
            returned_count=len(page),
            has_more=has_more,
            next_cursor=str(next_offset) if has_more else None,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目资源目录检索失败。")
        facts = safe_observation_facts(
            {
                "returned_count": int(output.get("returned_count") or 0),
                "has_more": bool(output.get("has_more")),
            }
        )
        return ToolObservationProjection(
            summary=f"找到 {facts['returned_count']} 个项目资源。",
            facts=facts,
            provider_payload=output,
        )
