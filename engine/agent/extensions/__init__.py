"""DataBox Agent extension framework — dynamic skill/tool discovery and loading.

Extensions let users and plugins contribute skills and tools without modifying
the engine source.  The framework is built on abstract *Sources* that discover
definitions from different locations (builtin dirs, user config, remote APIs).
"""

from engine.agent.extensions.discovery import (
    SkillSource,
    BuiltinSkillSource,
    UserSkillSource,
    DictSkillSource,
    ToolSource,
    BuiltinToolSource,
    UserToolSource,
    DictToolSource,
)
from engine.agent.extensions.loader import (
    load_skill_from_dict,
    load_skills_from_source,
    load_tool_spec_from_dict,
    load_tool_specs_from_source,
)

__all__ = [
    # Skill sources
    "SkillSource",
    "BuiltinSkillSource",
    "UserSkillSource",
    "DictSkillSource",
    # Tool sources
    "ToolSource",
    "BuiltinToolSource",
    "UserToolSource",
    "DictToolSource",
    # Loaders
    "load_skill_from_dict",
    "load_skills_from_source",
    "load_tool_spec_from_dict",
    "load_tool_specs_from_source",
]
