"""Abstract discovery sources for skills.

A *Source* knows WHERE to find definitions (directory, database, API)
but not HOW to validate them — that's the loader's job.

Sources return raw dicts.  The skill loader validates them into SkillSpec.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("dbfox.dbfox_agent.extensions.discovery")


class SkillSource(ABC):
    """Abstract source of skill definitions (raw dicts, not validated).

    Implementations discover skills from different locations:
    builtin directories, user config, project config, remote APIs, etc.
    """

    def __init__(self, *, priority: int = 0) -> None:
        self.priority = priority  # higher = loaded later = overrides lower

    @abstractmethod
    def discover(self) -> list[dict[str, Any]]:
        """Yield raw skill dicts from this source.

        Each dict must be validatable as a SkillSpec.  Invalid dicts are
        logged and skipped by the loader — they don't crash discovery.
        """
        ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__} priority={self.priority}>"


class BuiltinSkillSource(SkillSource):
    """Built-in skills shipped with the engine (engine/agent/skills/builtin/).

    Lowest priority — user/project skills override builtins with the same id.
    """

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(priority=0)
        if path is None:
            path = Path(__file__).resolve().parent.parent / "skills" / "builtin"
        self.path = path

    def discover(self) -> list[dict[str, Any]]:
        if not self.path.is_dir():
            logger.debug("Builtin skill dir not found: %s", self.path)
            return []
        results: list[dict[str, Any]] = []
        for yf in sorted(self.path.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    results.append(raw)
                else:
                    logger.warning("Skipping %s: expected mapping, got %s", yf.name, type(raw).__name__)
            except Exception as exc:
                logger.error("Failed to read skill file %s: %s", yf.name, exc)
        return results


class UserSkillSource(SkillSource):
    """User-defined skills from a configurable directory.

    Medium priority.  Typical paths:
    - ~/.dbfox/skills/        (global, per-user)
    - .dbfox/skills/          (project-level)
    """

    def __init__(self, path: str | Path, *, priority: int = 10) -> None:
        super().__init__(priority=priority)
        self.path = Path(path)

    def discover(self) -> list[dict[str, Any]]:
        if not self.path.is_dir():
            logger.debug("User skill dir not found: %s", self.path)
            return []
        results: list[dict[str, Any]] = []
        for yf in sorted(self.path.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    logger.info("Discovered user skill '%s' from %s", raw.get("id", "?"), yf)
                    results.append(raw)
                else:
                    logger.warning("Skipping %s: expected mapping, got %s", yf.name, type(raw).__name__)
            except Exception as exc:
                logger.error("Failed to read user skill file %s: %s", yf.name, exc)
        return results


class DictSkillSource(SkillSource):
    """Programmatic skill source — useful for tests, plugins, and inline definitions.

    Highest default priority so programmatic registrations override file-based ones.
    """

    def __init__(self, skills: list[dict[str, Any]] | None = None, *, priority: int = 100) -> None:
        super().__init__(priority=priority)
        self._skills: list[dict[str, Any]] = list(skills or [])

    def add(self, skill: dict[str, Any]) -> None:
        """Add a raw skill dict to this source."""
        self._skills.append(skill)

    def add_spec(self, skill_spec: Any) -> None:
        """Add a SkillSpec instance (will be serialized to dict)."""
        if hasattr(skill_spec, "model_dump"):
            self._skills.append(skill_spec.model_dump(mode="json"))
        else:
            self._skills.append(skill_spec)

    def discover(self) -> list[dict[str, Any]]:
        return list(self._skills)
