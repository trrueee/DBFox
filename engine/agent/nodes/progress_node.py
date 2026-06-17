from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.progress.fast_path import (
    check_escalate,
    check_sql_repair_fastpath,
    deterministic_progress_fastpath,
)
from engine.agent.progress.llm_judge import call_llm_judge
from engine.agent.progress.lens_formatter import enrich_progress_result

logger = logging.getLogger("dbfox.dbfox_agent.nodes.progress_node")


def judge_progress(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM Progress Judge — decides whether the task is complete after each observe.

    This node coordinates fast-paths (escalation, SQL repair, ReAct routing) and
    delegates semantic evaluation to the LLM judge when fast-paths do not apply.
    """
    ctx = graph_context(config)

    if not ctx.has_llm_credentials:
        raise RuntimeError("Progress judge requires LLM credentials.")

    # 1. Fast path: escalate.tool_group was called
    escalate_result = check_escalate(state)
    if escalate_result:
        return enrich_progress_result(escalate_result, state)

    # 2. Fast path: SQL / schema repair without LLM judge
    repair_result = check_sql_repair_fastpath(state)
    if repair_result:
        return enrich_progress_result(repair_result, state)

    # 3. Fast path: standard ReAct progress routing (e.g. tool observations, final answers)
    deterministic_result = deterministic_progress_fastpath(state)
    if deterministic_result:
        return enrich_progress_result(deterministic_result, state)

    # 4. Semantic LLM Judge fallback
    llm_result = call_llm_judge(state, config)
    return enrich_progress_result(llm_result, state)

