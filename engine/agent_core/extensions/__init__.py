"""DBFox Agent extension framework — dynamic skill discovery and loading.

Extensions let users and plugins contribute skills without modifying the engine
source.  The framework is built on abstract *Sources* that discover
definitions from different locations (builtin dirs, user config, remote APIs).
"""

from engine.agent_core.extensions.discovery import (
    SkillSource,
    BuiltinSkillSource,
    UserSkillSource,
    DictSkillSource,
)

__all__ = [
    # Skill sources (used by agent-layer SkillRegistry)
    "SkillSource",
    "BuiltinSkillSource",
    "UserSkillSource",
    "DictSkillSource",
]
