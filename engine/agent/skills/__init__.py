"""DBFox Agent skill layer.

Skills are curated execution patterns that give the ReAct model structured
guidance (tool boundaries, step sequences, success criteria, recovery playbooks)
while preserving its freedom to adapt.

Public API:
- get_skill_registry() → SkillRegistry (module-level singleton)
- SkillSpec, SkillRecoveryRule (Pydantic schemas)
- render_skill_for_planner / render_skill_for_model / render_recovery_for_progress
"""

from __future__ import annotations

from engine.agent.skills.registry import get_skill_registry, reset_skill_registry, SkillRegistry
from engine.agent.skills.schemas import SkillSpec, SkillRecoveryRule
from engine.agent.skills.renderer import (
    render_skill_for_planner,
    render_skill_for_model,
    render_recovery_for_progress,
    render_skill_list_for_planner,
)

__all__ = [
    "get_skill_registry",
    "reset_skill_registry",
    "SkillRegistry",
    "SkillSpec",
    "SkillRecoveryRule",
    "render_skill_for_planner",
    "render_skill_for_model",
    "render_recovery_for_progress",
    "render_skill_list_for_planner",
]
