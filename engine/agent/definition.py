"""Versioned Agent identity and execution policy."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.run import RunLimits


class TaskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analytical_markers: tuple[str, ...] = (
        "分析", "趋势", "变化", "增长", "下降", "对比", "比较", "分布", "异常", "原因",
        "转化", "留存", "同比", "环比", "排名", "占比", "相关性", "波动",
        "analyze", "trend", "change", "growth", "compare", "distribution", "anomaly",
        "cause", "conversion", "retention", "correlation", "ranking",
    )
    schema_markers: tuple[str, ...] = (
        "表结构", "字段", "有哪些表", "表关系", "外键", "索引",
        "schema", "column", "table structure", "foreign key", "index",
    )
    data_markers: tuple[str, ...] = (
        "sql", "数据库", "数据", "统计", "多少", "数量", "订单", "用户", "查询", "列出",
        "database", "data", "count", "total", "orders", "users", "query", "list",
    )
    require_coverage_review_for_analytical: bool = True


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "dbfox.data_analyst"
    version: str = "2.0"
    behavior: str = "autonomous_evidence_grounded_analysis"
    allowed_tool_groups: tuple[str, ...] = (
        "control",
        "environment",
        "schema",
        "db",
        "sql",
        "result",
        "chart",
    )
    execution_mode: str = "agent_autonomous_read"
    limits: RunLimits = Field(default_factory=RunLimits)
    task_policy: TaskPolicy = Field(default_factory=TaskPolicy)

    @property
    def hash(self) -> str:
        value = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


DEFAULT_AGENT_DEFINITION = AgentDefinition()
