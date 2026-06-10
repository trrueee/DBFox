"""Skill contract schemas — Pydantic models for DataBox Agent v2 Skill layer.

A Skill is a curated execution pattern that bundles:
- Tool-group boundaries (what's allowed, what's forbidden)
- Ordered step guidance (recommended tool sequence)
- Success criteria (for the Progress Judge)
- Recovery rules (what to do when things go wrong)
- Memory writeback rules (what to persist after success)

Skills are NOT hardcoded workflows. They are "task playbooks" that give the
ReAct model structured guidance while preserving its freedom to adapt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Recovery ──────────────────────────────────────────────────────────────────

class SkillRecoveryRule(BaseModel):
    """A single recovery rule: when <condition>, do <action>."""

    condition: str = Field(
        description=(
            "When this condition is detected (e.g. 'unknown_table', "
            "'empty_result', 'ambiguous_join')."
        ),
    )
    action: str = Field(
        description=(
            "What to do when the condition fires. "
            "E.g. 'schema.list_tables + schema.refresh_catalog', "
            "'loosen_time_filter + retry', 'ask_user_clarification'."
        ),
    )


# ── Memory writeback ──────────────────────────────────────────────────────────

class SkillWritebackRule(BaseModel):
    """What to persist to memory after a successful execution of this skill."""

    memory_type: str = Field(
        description=(
            "Type of memory to write: 'trajectory', 'semantic_definition', "
            "'schema_alias', 'join_path', 'metric_definition', 'query_pattern'."
        ),
    )
    trigger: str = Field(
        description=(
            "When to trigger this writeback. E.g. 'on_success', "
            "'on_user_confirmed', 'on_join_discovered'."
        ),
    )
    content_hint: str = Field(
        default="",
        description="Hint for the model about what to include in the memory entry.",
    )


# ── Skill specification ───────────────────────────────────────────────────────

class SkillSpec(BaseModel):
    """A curated execution pattern for a specific DataBox task type.

    Skills bridge the gap between "flat tool list" and "reliable execution":
    they give the ReAct model a tested tool sequence, safety boundaries,
    success criteria, and recovery playbooks for common failures.
    """

    id: str = Field(
        description="Unique skill identifier, e.g. 'safe_data_lookup'.",
    )
    name: str = Field(
        description="Human-readable name, e.g. 'Safe Data Lookup'.",
    )
    description: str = Field(
        description="One-paragraph summary of what this skill does and when to use it.",
    )

    # ── When to use ────────────────────────────────────────────────────────
    use_when: list[str] = Field(
        description="Semantic conditions that suggest this skill. Used by the Planner to select skills.",
    )

    # ── Tool boundaries ────────────────────────────────────────────────────
    allowed_tool_groups: list[str] = Field(
        description="Tool groups the ReAct model may use when this skill is active.",
    )
    forbidden_tool_groups: list[str] = Field(
        default_factory=list,
        description="Tool groups explicitly forbidden (e.g. 'execution' for review-only skills).",
    )

    # ── Recommended steps ──────────────────────────────────────────────────
    steps: list[str] = Field(
        description=(
            "Recommended tool sequence in order. Each entry is a tool name "
            "(e.g. 'environment.get_profile') or a tool group hint "
            "(e.g. 'schema.*'). The model may adapt the sequence, but this "
            "is the tested happy path."
        ),
    )

    # ── Success criteria ───────────────────────────────────────────────────
    success_criteria: list[str] = Field(
        description="Observable criteria the Progress Judge checks to determine completion.",
    )

    # ── Recovery playbook ──────────────────────────────────────────────────
    recovery: dict[str, list[SkillRecoveryRule]] = Field(
        default_factory=dict,
        description=(
            "Recovery rules keyed by failure category (e.g. 'unknown_table', "
            "'empty_result'). Each entry is a list of actions to try in order."
        ),
    )

    # ── Memory writeback ───────────────────────────────────────────────────
    writeback: list[SkillWritebackRule] = Field(
        default_factory=list,
        description="Memory entries to write after successful execution.",
    )


# ── Skill manifest (registry container) ───────────────────────────────────────

class SkillManifest(BaseModel):
    """Container for a collection of skills. Used to load/validate all builtins."""

    skills: list[SkillSpec] = Field(
        description="All skills in this manifest.",
    )
