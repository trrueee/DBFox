"""Semantic tools registered into the agent tool registry.

These tools let the ReAct agent invoke semantic resolution during a run.
"""

from __future__ import annotations

from typing import Any

from engine.agent_core.types import ToolObservation
from engine.agent_core.tool_registry import ToolContext
from engine.semantic.resolver import SemanticResolver

# Module-level singleton — resolver needs a db per call, so we create it
# fresh each time from the ToolContext.


def semantic_resolve(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Resolve business semantics for the current user question.

    Maps business terms, metrics, dimensions, filters, and join paths
    to actual database objects using LLM understanding + catalog verification.

    Input: none required (reads question from state, datasource from context).
    Output: SemanticResolution with resolved_terms, resolved_metrics,
            resolved_dimensions, candidate_tables, join_paths, ambiguity,
            and semantic_context_text.
    """
    datasource_id = str(ctx.state.get("datasource_id") or "")
    question = str(
        args.get("question")
        or ctx.state.get("question")
        or ctx.request.question
    )

    workspace = ctx.state.get("workspace_context")

    # Get model config from request
    api_key = getattr(ctx.request, "api_key", None) if ctx.request else None
    api_base = getattr(ctx.request, "api_base", None) if ctx.request else None
    model_name = getattr(ctx.request, "model_name", None) if ctx.request else None

    try:
        resolver = SemanticResolver(ctx.db)
        resolution = resolver.resolve(
            question=question,
            datasource_id=datasource_id,
            workspace_context=workspace if isinstance(workspace, dict) else None,
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
        )

        return ToolObservation(
            name="semantic.resolve",
            status="success",
            input=args,
            output=resolution.model_dump(mode="json"),
            latency_ms=0,
        )
    except Exception as exc:
        return ToolObservation(
            name="semantic.resolve",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=0,
        )
