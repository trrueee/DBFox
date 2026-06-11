from __future__ import annotations

from typing import Any

from engine.agent.graph.state import DataBoxAgentState
from engine.agent.planning.schemas import (
    AgentExecutionMode,
    AgentGroundingLevel,
    AgentPlanDirective,
    AgentTaskType,
    AgentToolGroup,
)
from engine.agent.graph.message_utils import first_user_text


SCHEMA_KEYWORDS = (
    "schema", "describe", "columns", "fields", "table structure",
    "what tables", "list tables", "primary key", "foreign key",
    "表结构", "字段", "列", "有哪些表", "有哪些字段", "建表",
)
SQL_REPAIR_KEYWORDS = (
    "fix", "repair", "error", "failed", "failure", "wrong", "not working",
    "报错", "修复", "失败", "不对",
)
SQL_OPTIMIZE_KEYWORDS = (
    "optimize", "rewrite", "refactor sql", "优化", "重写",
)
SQL_GENERATE_KEYWORDS = (
    "sql", "query", "generate sql", "write sql", "写sql", "生成sql",
)
CHART_KEYWORDS = (
    "chart", "plot", "visualize", "visualization", "graph", "bar chart",
    "line chart", "pie chart", "图表", "画图", "可视化", "柱状图", "折线图", "饼图",
)
DATA_LOOKUP_KEYWORDS = (
    "count", "sum", "avg", "average", "total", "top", "rank", "trend",
    "revenue", "sales", "by status", "per month",
    "查", "查询", "统计", "多少", "总数", "平均", "汇总", "收入", "用户数",
    "销售额", "排名", "趋势",
)
RESULT_ANALYSIS_KEYWORDS = (
    "result", "explain result", "analyze result", "insight", "anomaly",
    "结果", "分析结果", "洞察", "异常",
)
PRODUCT_HELP_KEYWORDS = (
    "how do i", "how to", "help", "usage", "docs", "功能", "怎么用", "帮助",
)


def build_deterministic_plan(state: DataBoxAgentState) -> AgentPlanDirective:
    """Build a cheap initial plan from request context.

    This router intentionally does not try to be a semantic planner. It only
    chooses a safe starting tool scope; the ReAct model can request more scope
    later through escalate.tool_group.
    """

    text = first_user_text(state.get("messages", []))
    lowered = text.lower()
    workspace = state.get("workspace_context") or {}
    execute = bool(state.get("execute"))

    task_type = _classify_task(lowered, workspace, bool(state.get("datasource_id")))
    groups = _tool_groups(task_type, execute)
    grounding_level = _grounding_level(task_type, execute, workspace)
    execution_mode = _execution_mode(task_type, execute, groups)
    skill_ids = _selected_skill_ids(task_type)

    return AgentPlanDirective(
        task_type=task_type,
        grounding_level=grounding_level,
        execution_mode=execution_mode,
        allowed_tool_groups=groups,
        should_call_tools=bool(groups),
        should_execute_sql=execute and "execution" in groups,
        needs_clarification=False,
        clarification_question=None,
        success_criteria=[_success_criterion(task_type)],
        risk_notes=[] if execute else ["Execution disabled; do not run SQL."],
        selected_skill_ids=skill_ids,
        reasoning_summary=f"Deterministic route selected task_type={task_type}.",
    )


def should_use_llm_planner(state: DataBoxAgentState) -> bool:
    """Return True only when deterministic routing needs semantic recovery."""

    progress = state.get("progress_decision") or {}
    if progress.get("status") != "replan":
        return False

    if progress.get("should_ask_user"):
        return True

    failure_layer = progress.get("failure_layer")
    if failure_layer in {"planner", "semantic", "unknown"}:
        return True

    if progress.get("revised_plan_hint") and not progress.get("next_tool_groups"):
        return True

    return False


def _classify_task(text: str, workspace: dict[str, Any], has_datasource: bool) -> AgentTaskType:
    active_sql = bool(workspace.get("active_sql") or workspace.get("selected_sql"))
    last_error = bool(workspace.get("last_error"))
    result_preview = bool(workspace.get("last_query_result_preview"))

    if active_sql and (last_error or _has_any(text, SQL_REPAIR_KEYWORDS)):
        return "sql_repair"

    if active_sql and _has_any(text, SQL_OPTIMIZE_KEYWORDS):
        return "sql_optimization"

    if result_preview and _has_any(text, RESULT_ANALYSIS_KEYWORDS):
        return "result_analysis"

    if active_sql and _has_any(text, SQL_GENERATE_KEYWORDS + RESULT_ANALYSIS_KEYWORDS):
        return "workspace_explanation"

    if _has_any(text, CHART_KEYWORDS):
        return "chart_suggestion"

    if _has_any(text, SCHEMA_KEYWORDS) and not _has_any(text, DATA_LOOKUP_KEYWORDS):
        return "schema_understanding"

    if _has_any(text, SQL_REPAIR_KEYWORDS) and _has_any(text, SQL_GENERATE_KEYWORDS):
        return "sql_repair"

    if _has_any(text, SQL_OPTIMIZE_KEYWORDS) and _has_any(text, SQL_GENERATE_KEYWORDS):
        return "sql_optimization"

    if _has_any(text, SQL_GENERATE_KEYWORDS) and not _has_any(text, DATA_LOOKUP_KEYWORDS):
        return "sql_generation"

    if has_datasource and (_has_any(text, DATA_LOOKUP_KEYWORDS) or _looks_like_data_question(text)):
        return "data_lookup"

    if not has_datasource and _has_any(text, PRODUCT_HELP_KEYWORDS):
        return "product_help"

    return "data_lookup" if has_datasource else "chat"


def _tool_groups(task_type: AgentTaskType, execute: bool) -> list[AgentToolGroup]:
    groups_by_task: dict[AgentTaskType, list[AgentToolGroup]] = {
        "chat": [],
        "product_help": [],
        "database_concept": [],
        "workspace_explanation": ["workspace", "answer"],
        "schema_understanding": ["environment", "schema", "answer"],
        "semantic_analysis": ["environment", "schema", "semantic", "answer"],
        "sql_generation": [
            "environment", "schema", "semantic", "query_plan",
            "sql_generation", "sql_validation", "sql_repair", "answer",
        ],
        "sql_repair": [
            "workspace", "environment", "schema", "semantic", "query_plan",
            "sql_generation", "sql_validation", "sql_repair", "answer",
        ],
        "sql_optimization": [
            "workspace", "schema", "query_plan", "sql_generation",
            "sql_validation", "sql_repair", "answer",
        ],
        "data_lookup": [
            "environment", "schema", "semantic", "query_plan",
            "sql_generation", "sql_validation", "sql_repair", "result", "answer",
        ],
        "result_analysis": ["result", "chart", "answer"],
        "chart_suggestion": [
            "environment", "schema", "semantic", "query_plan",
            "sql_generation", "sql_validation", "sql_repair", "result", "chart", "answer",
        ],
        "ambiguous": ["schema", "answer"],
    }

    groups = list(groups_by_task[task_type])
    if execute and task_type in {
        "data_lookup", "chart_suggestion", "sql_generation",
        "sql_repair", "sql_optimization",
    }:
        groups.append("execution")
    return list(dict.fromkeys(groups))


def _grounding_level(
    task_type: AgentTaskType,
    execute: bool,
    workspace: dict[str, Any],
) -> AgentGroundingLevel:
    if task_type in {"chat", "product_help", "database_concept"}:
        return "none"
    if task_type in {"workspace_explanation", "sql_repair"} and workspace:
        return "workspace"
    if task_type in {"schema_understanding", "sql_generation", "sql_optimization"}:
        return "schema"
    if task_type == "semantic_analysis":
        return "semantic"
    if task_type in {"data_lookup", "chart_suggestion", "result_analysis"}:
        return "data" if execute or task_type == "result_analysis" else "schema"
    return "schema"


def _execution_mode(
    task_type: AgentTaskType,
    execute: bool,
    groups: list[AgentToolGroup],
) -> AgentExecutionMode:
    if not groups:
        return "none"
    if execute and task_type in {
        "data_lookup", "chart_suggestion", "sql_generation",
        "sql_repair", "sql_optimization",
    }:
        return "user_requested_read"
    return "suggest_only"


def _selected_skill_ids(task_type: AgentTaskType) -> list[str]:
    if task_type == "schema_understanding":
        return ["schema_exploration"]
    if task_type == "data_lookup":
        return ["safe_data_lookup"]
    if task_type == "result_analysis":
        return ["result_analysis"]
    if task_type == "chart_suggestion":
        return ["safe_data_lookup", "result_analysis"]
    if task_type == "semantic_analysis":
        return ["semantic_resolution"]
    return []


def _success_criterion(task_type: AgentTaskType) -> str:
    criteria = {
        "chat": "User receives a direct conversational answer.",
        "product_help": "User receives actionable product guidance.",
        "database_concept": "User receives a concise database concept explanation.",
        "workspace_explanation": "Workspace context is explained without querying unrelated data.",
        "schema_understanding": "Relevant tables or columns are described from catalog evidence.",
        "semantic_analysis": "Business terms are mapped to database objects or flagged as unresolved.",
        "sql_generation": "SQL is generated and validated without unsafe execution.",
        "sql_repair": "SQL issue is repaired or explained with evidence.",
        "sql_optimization": "SQL is improved or explained with validation context.",
        "data_lookup": "User's data question is answered with grounded evidence.",
        "result_analysis": "Existing result data is profiled and explained.",
        "chart_suggestion": "A suitable chart is suggested or produced from grounded data.",
        "ambiguous": "Agent explores available context before asking the user.",
    }
    return criteria[task_type]


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _looks_like_data_question(text: str) -> bool:
    return "?" in text and any(word in text for word in ("show", "find", "get", "list"))
