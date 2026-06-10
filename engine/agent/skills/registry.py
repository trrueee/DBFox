"""Skill registry — loads, validates, and queries DataBox Agent Skills.

Skills can come from multiple sources:
- Builtin: engine/agent/skills/builtin/*.yaml  (priority 0)
- User global: ~/.databox/skills/*.yaml       (priority 10)
- Project: .databox/skills/*.yaml              (priority 20)
- Programmatic: registry.register(spec)         (highest priority)

Higher-priority sources override lower-priority skills with the same id.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from engine.agent.skills.schemas import SkillSpec
from engine.agent.extensions.discovery import (
    SkillSource,
    BuiltinSkillSource,
    UserSkillSource,
    DictSkillSource,
)
from engine.agent.extensions.loader import load_skills_from_source

logger = logging.getLogger("databox.databox_agent.skills.registry")

_BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


class SkillRegistry:
    """In-memory registry of all available DataBox Agent Skills.

    Skills are loaded from multiple configurable sources.  Sources with higher
    priority override lower-priority skills with the same id — a user skill
    with the same id as a builtin replaces it.

    Thread-safe after initialization.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}
        self._sources: list[SkillSource] = []
        self._loaded: bool = False

    # ── Source management ──────────────────────────────────────────────────────

    def add_source(self, source: SkillSource) -> "SkillRegistry":
        """Register a discovery source.  Call before load_all().

        Sources are loaded in priority order (low to high).  When two sources
        define the same skill id, the higher-priority one wins.
        """
        self._sources.append(source)
        self._sources.sort(key=lambda s: s.priority)
        return self

    def add_builtin_source(self, path: Path | None = None) -> "SkillRegistry":
        """Register the builtin skill directory (priority 0)."""
        return self.add_source(BuiltinSkillSource(path or _BUILTIN_DIR))

    def add_user_source(self, path: str | Path, *, priority: int = 10) -> "SkillRegistry":
        """Register a user/project skill directory."""
        return self.add_source(UserSkillSource(path, priority=priority))

    def add_dict_source(self, skills: list[dict[str, Any]] | None = None,
                        *, priority: int = 100) -> DictSkillSource:
        """Register a programmatic source and return it for further mutation."""
        src = DictSkillSource(skills, priority=priority)
        self.add_source(src)
        return src

    # ── Load ───────────────────────────────────────────────────────────────────

    def load_all(self) -> list[SkillSpec]:
        """Load skills from all registered sources.

        Idempotent — subsequent calls return the cached result.
        Reset with clear() if you need to reload after adding sources.
        """
        if self._loaded:
            return list(self._skills.values())

        if not self._sources:
            # Convenience: if no sources were registered, auto-add builtins.
            self.add_builtin_source()

        total = 0
        for source in sorted(self._sources, key=lambda s: s.priority):
            loaded = load_skills_from_source(source)
            for skill in loaded:
                existing = self._skills.get(skill.id)
                if existing is not None:
                    logger.info(
                        "Skill '%s' overridden by source %s (priority %d)",
                        skill.id, source, source.priority,
                    )
                self._skills[skill.id] = skill
                total += 1

        self._loaded = True
        logger.info("SkillRegistry: loaded %d skills from %d sources.",
                     len(self._skills), len(self._sources))
        return list(self._skills.values())

    # ── Registration (programmatic) ────────────────────────────────────────────

    def register(self, skill: SkillSpec) -> "SkillRegistry":
        """Directly register a SkillSpec.  Overrides any source-loaded skill
        with the same id regardless of priority.

        Raises nothing — always succeeds.
        """
        if skill.id in self._skills:
            logger.info("Skill '%s' overridden by programmatic register().", skill.id)
        self._skills[skill.id] = skill
        return self

    def register_dict(self, raw: dict[str, Any]) -> SkillSpec | None:
        """Validate and register a raw dict.  Returns the spec on success, None on failure."""
        from engine.agent.extensions.loader import load_skill_from_dict
        spec = load_skill_from_dict(raw)
        if spec is not None:
            self.register(spec)
        return spec

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill.  Returns True if it existed."""
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False

    # ── Query ──────────────────────────────────────────────────────────────────

    def get(self, skill_id: str) -> SkillSpec | None:
        if not self._loaded:
            self.load_all()
        return self._skills.get(skill_id)

    def list_all(self) -> list[SkillSpec]:
        if not self._loaded:
            self.load_all()
        return list(self._skills.values())

    def find_by_tool_group(self, tool_group: str) -> list[SkillSpec]:
        if not self._loaded:
            self.load_all()
        return [s for s in self._skills.values() if tool_group in s.allowed_tool_groups]

    def find_by_trigger(self, condition: str) -> list[SkillSpec]:
        if not self._loaded:
            self.load_all()
        cl = condition.lower()
        return [s for s in self._skills.values()
                if any(cl in uw.lower() for uw in s.use_when)]

    def summarize_for_planner(self) -> list[dict[str, Any]]:
        if not self._loaded:
            self.load_all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "use_when": s.use_when,
                "allowed_tool_groups": s.allowed_tool_groups,
                "forbidden_tool_groups": s.forbidden_tool_groups,
                "success_criteria": s.success_criteria,
            }
            for s in self._skills.values()
        ]

    def clear(self) -> None:
        """Clear all loaded skills and reset loaded flag.  For tests / reloads."""
        self._skills.clear()
        self._loaded = False

    # ── Dunder ─────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def __repr__(self) -> str:
        return f"<SkillRegistry skills={len(self._skills)} sources={len(self._sources)} loaded={self._loaded}>"


# ── Module-level singleton ────────────────────────────────────────────────────

_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Return the module-level SkillRegistry singleton.

    On first call, auto-configures sources:
    1. Builtin (priority 0)
    2. User global ~/.databox/skills/ (priority 10)
    3. Project .databox/skills/ (priority 20)
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.add_builtin_source()
        # User global skills
        _registry.add_user_source(Path.home() / ".databox" / "skills", priority=10)
        # Project-local skills (only if cwd is accessible)
        try:
            cwd = Path.cwd()
            project_dir = cwd / ".databox" / "skills"
            if project_dir.is_dir():
                _registry.add_user_source(project_dir, priority=20)
        except Exception:
            pass  # cwd may not exist in some environments
        _registry.load_all()
    return _registry


def reset_skill_registry() -> None:
    """Reset the singleton (mainly for tests)."""
    global _registry
    _registry = None
