"""Versioned, provider-neutral AgentBench dataset contracts."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetRole(StrEnum):
    DEVELOPMENT = "development"
    REGRESSION = "regression"
    HIDDEN_HOLDOUT = "hidden_holdout"
    PRODUCTION_CANARY = "production_canary"
    CALIBRATION = "calibration"


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNSCORED = "unscored"


class ComparisonMode(StrEnum):
    EXACT = "exact"
    SUBSET = "subset"


class AnswerExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_terms: tuple[str, ...] = ()
    any_of_terms: tuple[tuple[str, ...], ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    required_numbers: tuple[float, ...] = ()
    require_nonempty: bool = True


class ResultExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    golden_sql: str
    comparison: ComparisonMode = ComparisonMode.EXACT
    ordered: bool = False
    allow_extra_columns: bool = True
    absolute_tolerance: float = Field(default=1e-9, ge=0)
    relative_tolerance: float = Field(default=1e-9, ge=0)

    @model_validator(mode="after")
    def validate_read_only_sql(self) -> "ResultExpectation":
        value = self.golden_sql.strip().lower()
        if not (value.startswith("select") or value.startswith("with")):
            raise ValueError("AgentBench golden_sql must be a read-only SELECT/CTE")
        return self


class TraceExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    terminal_statuses: tuple[str, ...] = ("completed",)
    all_run_statuses: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    any_of_required_tools: tuple[tuple[str, ...], ...] = ()
    any_of_attempted_tools: tuple[tuple[str, ...], ...] = ()
    required_error_codes: tuple[str, ...] = ()
    required_tool_subsequence: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    forbidden_artifacts: tuple[str, ...] = ()
    max_tool_calls: int = Field(default=12, ge=0)
    max_turns: int = Field(default=14, ge=1)
    max_failed_tool_calls: int = Field(default=3, ge=0)
    max_duplicate_tool_calls: int | None = Field(default=None, ge=0)
    max_duplicate_query_fingerprints: int | None = Field(default=None, ge=0)
    require_valid_citations: bool = True
    min_citations: int = Field(default=0, ge=0)
    limit_scope: Literal["all_runs", "final_run"] = "all_runs"


class SafetyExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_unchanged_sql: tuple[str, ...] = ()
    forbidden_output_terms: tuple[str, ...] = ()
    require_no_write: bool = True


class ResourceBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens: int | None = Field(default=None, ge=1)
    max_latency_ms: int | None = Field(default=None, ge=1)
    scope: Literal["all_runs", "final_run"] = "all_runs"


class PlanExpectation(BaseModel):
    """Opt-in contract for tasks that should expose a durable public plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: bool = False
    min_versions: int = Field(default=1, ge=1)
    terminal_statuses: tuple[str, ...] = ("completed", "partial")
    max_skipped_steps: int | None = Field(default=None, ge=0)
    require_stable_step_ids: bool = True


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    category: str = Field(min_length=2, max_length=80)
    capability: str = Field(min_length=2, max_length=120)
    prompts: tuple[str, ...] = Field(min_length=1)
    tags: frozenset[str] = frozenset()
    history: tuple[HistoryMessage, ...] = ()
    answer: AnswerExpectation = Field(default_factory=AnswerExpectation)
    result: ResultExpectation | None = None
    trace: TraceExpectation = Field(default_factory=TraceExpectation)
    safety: SafetyExpectation = Field(default_factory=SafetyExpectation)
    budget: ResourceBudget = Field(default_factory=ResourceBudget)
    plan: PlanExpectation = Field(default_factory=PlanExpectation)
    # This is intentionally a case-level evaluation expectation, not a Context
    # policy.  It lets the paired smoke runner distinguish an expected safe
    # omission from a v4 runtime that silently failed to contribute context.
    # Explicitly opt in to current-request authority evidence.  This belongs
    # to the versioned dataset contract rather than to a case-id convention.
    notes: str = ""

    @model_validator(mode="after")
    def validate_prompts(self) -> "EvalCase":
        if any(not prompt.strip() for prompt in self.prompts):
            raise ValueError("AgentBench prompts cannot be blank")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,99}$")
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    role: DatasetRole
    seed_version: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1)
    cases: tuple[EvalCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "DatasetManifest":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("AgentBench case_id values must be unique")
        if self.role is DatasetRole.HIDDEN_HOLDOUT:
            for case in self.cases:
                if "revealed" in case.tags:
                    raise ValueError("A hidden holdout cannot contain revealed cases")
        return self

    def select(
        self,
        *,
        tags: frozenset[str] = frozenset(),
        case_ids: frozenset[str] = frozenset(),
    ) -> tuple[EvalCase, ...]:
        selected = self.cases
        if tags:
            selected = tuple(case for case in selected if tags <= case.tags)
        if case_ids:
            selected = tuple(case for case in selected if case.case_id in case_ids)
        return tuple(selected)


def load_manifest(path: Path) -> DatasetManifest:
    """Load and strictly validate one immutable dataset manifest."""

    return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))


def public_manifest_summary(manifest: DatasetManifest) -> dict[str, Any]:
    """Return metadata safe for reports without prompts, history or goldens."""

    return {
        "schema_version": manifest.schema_version,
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "role": manifest.role.value,
        "seed_version": manifest.seed_version,
        "case_count": len(manifest.cases),
        "categories": sorted({case.category for case in manifest.cases}),
    }
