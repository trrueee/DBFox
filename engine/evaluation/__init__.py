"""DBFox Agent Eval Layer — quality evaluation for the full agent trajectory.

Modules:
  schemas             — AgentEvalCase, AgentEvalInput, AgentEvalExpectation
  local_runner        — LocalEvalRunner (deterministic, no LLM required)
  langsmith_adapter   — LangSmith dataset / experiment / feedback sync
  agent_eval          — DB-backed golden task eval runner (legacy)
  agent_case_evaluator— Per-case evaluator for golden tasks (legacy)
  evaluators/         — Per-dimension evaluators: planner, trajectory, policy, sql, artifact, answer
  datasets/           — JSON eval case files
"""

from engine.evaluation.schemas import (
    AgentEvalCase,
    AgentEvalCaseResult,
    AgentEvalExpectation,
    AgentEvalInput,
    AnswerExpectation,
    ArtifactExpectation,
    PlannerExpectation,
    PolicyExpectation,
    SQLExpectation,
    SemanticExpectation,
    TrajectoryExpectation,
)
from engine.evaluation.local_runner import LocalEvalRunner
from engine.evaluation.langsmith_adapter import LangSmithAdapter

__all__ = [
    "AgentEvalCase",
    "AgentEvalCaseResult",
    "AgentEvalExpectation",
    "AgentEvalInput",
    "AnswerExpectation",
    "ArtifactExpectation",
    "LangSmithAdapter",
    "LocalEvalRunner",
    "PlannerExpectation",
    "PolicyExpectation",
    "SQLExpectation",
    "SemanticExpectation",
    "TrajectoryExpectation",
]
