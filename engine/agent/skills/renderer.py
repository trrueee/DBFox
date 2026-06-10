"""Skill renderer — converts SkillSpec into structured prompt context.

Different consumers need different levels of detail:
- Planner: compact summary (id, name, use_when, tool boundaries)
- Model: full playbook (steps, success criteria, recovery rules)
- Progress Judge: success criteria + recovery playbook
"""

from __future__ import annotations

from engine.agent.skills.schemas import SkillSpec, SkillRecoveryRule


def render_skill_for_planner(skill: SkillSpec) -> str:
    """Compact skill description for the Planner prompt.

    The Planner needs enough to select the right skill without
    consuming excessive context window.
    """
    lines = [
        f"### Skill: {skill.name} (`{skill.id}`)",
        f"**Description**: {skill.description}",
        f"**Use when**: {', '.join(skill.use_when)}",
        f"**Allowed tool groups**: {', '.join(skill.allowed_tool_groups)}",
    ]
    if skill.forbidden_tool_groups:
        lines.append(f"**Forbidden tool groups**: {', '.join(skill.forbidden_tool_groups)}")
    if skill.success_criteria:
        lines.append(f"**Success criteria**: {', '.join(skill.success_criteria)}")
    return "\n".join(lines)


def render_skill_for_model(skill: SkillSpec) -> str:
    """Full skill playbook for the Model node.

    The model gets ordered steps, success criteria, and recovery rules
    so it can execute the skill with clear guidance.
    """
    lines = [
        f"## Active Skill: {skill.name}",
        f"**Goal**: {skill.description}",
        "",
        "### Recommended Tool Sequence",
    ]
    for i, step in enumerate(skill.steps, 1):
        lines.append(f"{i}. `{step}`")

    lines.append("")
    lines.append("### Success Criteria")
    for sc in skill.success_criteria:
        lines.append(f"- {sc}")

    if skill.recovery:
        lines.append("")
        lines.append("### Recovery Playbook")
        for category, rules in skill.recovery.items():
            lines.append(f"**When `{category}`**:")
            for rule in rules:
                lines.append(f"  - {rule.condition} → {rule.action}")

    if skill.forbidden_tool_groups:
        lines.append("")
        lines.append(f"### Forbidden: {', '.join(skill.forbidden_tool_groups)}")

    return "\n".join(lines)


def render_recovery_for_progress(skill: SkillSpec) -> str:
    """Render only the recovery playbook for the Progress Judge.

    When a failure occurs, the Progress Judge can reference this to
    suggest recovery_strategy and next_tool_groups.
    """
    if not skill.recovery:
        return ""

    lines = ["## Skill Recovery Playbook"]
    for category, rules in skill.recovery.items():
        lines.append(f"### {category}")
        for rule in rules:
            lines.append(f"- **{rule.condition}**: {rule.action}")
    return "\n".join(lines)


def render_skill_list_for_planner(skills: list[SkillSpec]) -> str:
    """Render a compact list of all available skills for the Planner."""
    if not skills:
        return "No skills available."
    return "\n\n".join(render_skill_for_planner(s) for s in skills)
