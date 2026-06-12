from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DisplayComponent = Literal["metric", "chart", "table", "markdown", "recommendation", "sql", "trace"]


class DisplayPlanItem(BaseModel):
    """Artifact-level rendering intent.

    This is not UI code. It tells the frontend which existing fixed component
    categories should be useful for the current answer.
    """

    component: DisplayComponent
    reason: str
    priority: int = 100


def build_display_plan(
    *,
    question: str,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: Any | None,
    chart_suggestion: dict[str, Any] | None = None,
    suggestions: list[Any] | None = None,
    error: str | None = None,
) -> list[DisplayPlanItem]:
    """Build a stable display plan from evidence artifacts.

    The LLM may decide whether to call `analysis.compose`, but this function
    keeps the final rendering intent deterministic and safe.
    """
    if error:
        return [
            DisplayPlanItem(component="markdown", reason="Explain why the analysis could not complete.", priority=10),
            DisplayPlanItem(component="trace", reason="Show the failed stage and recovery context.", priority=90),
        ]

    execution_success = bool((execution or {}).get("success"))
    row_count = int((execution or {}).get("rowCount") or 0) if execution else 0
    columns = list((execution or {}).get("columns") or []) if execution else []
    question_l = question.lower()
    chart_type = str((chart_suggestion or {}).get("type") or "").lower()
    has_chart = bool(chart_suggestion and chart_type and chart_type != "table")
    has_suggestions = bool(suggestions)

    plan: list[DisplayPlanItem] = []

    if execution_success:
        plan.append(DisplayPlanItem(
            component="metric",
            reason="Surface headline delivery quality and result-size signals before detailed evidence.",
            priority=10,
        ))

    if has_chart or _looks_like_visual_analysis(question_l, row_count, columns):
        plan.append(DisplayPlanItem(
            component="chart",
            reason="The task benefits from visual comparison, trend, distribution, or share analysis.",
            priority=20,
        ))

    if execution_success:
        plan.append(DisplayPlanItem(
            component="table",
            reason="Keep the query result visible as evidence for the answer.",
            priority=30,
        ))

    plan.append(DisplayPlanItem(
        component="markdown",
        reason="Provide human-readable interpretation, caveats, and key findings.",
        priority=40,
    ))

    if has_suggestions or _looks_like_open_ended_analysis(question_l):
        plan.append(DisplayPlanItem(
            component="recommendation",
            reason="Offer useful next questions or follow-up analysis paths.",
            priority=50,
        ))

    if sql:
        plan.append(DisplayPlanItem(
            component="sql",
            reason="Expose the SQL for reproducibility and review.",
            priority=80,
        ))

    if safety or row_count > 1 or _looks_like_complex_question(question_l):
        plan.append(DisplayPlanItem(
            component="trace",
            reason="Make schema selection, SQL validation, and analysis steps auditable.",
            priority=90,
        ))

    return _dedupe_by_component(plan)


def _looks_like_visual_analysis(question_l: str, row_count: int, columns: list[Any]) -> bool:
    if row_count > 1 and len(columns) >= 2:
        return True
    keywords = [
        "trend", "趋势", "变化", "对比", "compare", "ranking", "排名", "top", "占比", "share", "distribution", "分布",
        "按周", "按月", "按天", "环比", "同比", "异常", "anomaly",
    ]
    return any(keyword in question_l for keyword in keywords)


def _looks_like_open_ended_analysis(question_l: str) -> bool:
    keywords = ["为什么", "原因", "建议", "下一步", "优化", "分析", "洞察", "异常", "怎么", "如何", "why", "recommend"]
    return any(keyword in question_l for keyword in keywords)


def _looks_like_complex_question(question_l: str) -> bool:
    keywords = ["join", "漏斗", "留存", "cohort", "趋势", "对比", "排名", "异常", "分布", "分析", "优化"]
    return any(keyword in question_l for keyword in keywords)


def _dedupe_by_component(plan: list[DisplayPlanItem]) -> list[DisplayPlanItem]:
    seen: set[str] = set()
    result: list[DisplayPlanItem] = []
    for item in sorted(plan, key=lambda x: x.priority):
        if item.component in seen:
            continue
        seen.add(item.component)
        result.append(item)
    return result
