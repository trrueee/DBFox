"""Skill loading utilities — validate raw dicts into SkillSpec.

This module lives in the agent layer because it validates the stable
Agent-owned SkillSpec contract.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.agent.skills.schemas import SkillSpec

logger = logging.getLogger("dbfox.dbfox_agent.skills.loader")


def load_skill_from_dict(raw: dict[str, Any]) -> SkillSpec | None:
    """Validate a raw dict into a SkillSpec.  Returns None on failure."""
    try:
        return SkillSpec.model_validate(raw)
    except Exception as exc:
        skill_id = raw.get("id", "?")
        logger.error("Failed to validate skill '%s': %s", skill_id, exc)
        return None


def load_skills_from_source(source) -> list[SkillSpec]:
    """Discover raw dicts from a source and validate them into SkillSpecs.

    Invalid entries are logged and skipped — the caller gets only valid skills.
    """
    loaded: list[SkillSpec] = []
    for raw in source.discover():
        spec = load_skill_from_dict(raw)
        if spec is not None:
            loaded.append(spec)
    return loaded
