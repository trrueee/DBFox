"""DBFox Agent extension framework — dynamic skill/tool discovery and loading.

Extensions let users and plugins contribute skills and tools without modifying
the engine source.  The framework is built on abstract *Sources* that discover
definitions from different locations (builtin dirs, user config, remote APIs).
"""

from engine.agent_core.extensions.discovery import (
    SkillSource,
    BuiltinSkillSource,
    UserSkillSource,
    DictSkillSource,
    ToolSource,
    BuiltinToolSource,
    UserToolSource,
    DictToolSource,
)
from engine.agent_core.extensions.loader import (
    load_tool_spec_from_dict,
    load_tool_specs_from_source,
)

__all__ = [
    # Skill sources (used by agent-layer SkillRegistry)
    "SkillSource",
    "BuiltinSkillSource",
    "UserSkillSource",
    "DictSkillSource",
    # Tool sources (used by agent_core ToolRegistry)
    "ToolSource",
    "BuiltinToolSource",
    "UserToolSource",
    "DictToolSource",
    # Tool loaders (agent_core — no agent deps)
    "load_tool_spec_from_dict",
    "load_tool_specs_from_source",
]
