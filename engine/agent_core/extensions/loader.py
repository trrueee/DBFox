"""Tool loading utilities — validate raw dicts into ToolSpec.

The loader is the validation layer between discovery (raw dicts) and the
registry (validated ToolSpec).  Invalid entries are logged and skipped —
they never crash the loader.

Skill loading lives in engine.agent.skills.loader (agent layer) because
it depends on SkillSpec.  Tool loading lives here in agent_core because
ToolSpec and friends are agent_core types.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.agent_core.tool_registry import (
    ToolSpec,
    ToolPolicy,
    ToolExecutionSpec,
    ToolStateBinding,
)

logger = logging.getLogger("databox.databox_agent.extensions.loader")


# ── Tool loading ───────────────────────────────────────────────────────────────

REQUIRED_TOOL_FIELDS = {"name", "description", "handler"}


def load_tool_spec_from_dict(raw: dict[str, Any]) -> ToolSpec | None:
    """Validate a raw dict into a ToolSpec.  Returns None on failure.

    The raw dict must have at minimum: name, description, handler.
    The handler field is a reference string — it will be resolved to a
    callable later via HandlerRegistry.
    """
    missing = REQUIRED_TOOL_FIELDS - set(raw.keys())
    if missing:
        logger.error("Tool spec missing required fields: %s", missing)
        return None

    try:
        policy_raw = raw.get("policy") or {}
        policy = ToolPolicy(
            side_effect=policy_raw.get("side_effect", "none"),
            risk_level=policy_raw.get("risk_level", "safe"),
            requires_approval=policy_raw.get("requires_approval", False),
            requires_validated_sql=policy_raw.get("requires_validated_sql", False),
            allowed_execution_modes=policy_raw.get("allowed_execution_modes", []),
        )

        exec_raw = raw.get("execution") or {}
        execution = ToolExecutionSpec(
            timeout_seconds=exec_raw.get("timeout_seconds", 30),
            idempotent=exec_raw.get("idempotent", True),
            retryable=exec_raw.get("retryable", False),
            max_retries=exec_raw.get("max_retries", 0),
            concurrency=exec_raw.get("concurrency", "sequential"),
        )

        binding_raw = raw.get("binding") or {}
        binding = ToolStateBinding(
            consumes_state_keys=binding_raw.get("consumes_state_keys", []),
            produces_state_keys=binding_raw.get("produces_state_keys", []),
            artifact_types=binding_raw.get("artifact_types", []),
        )

        contract_raw = raw.get("state_contract") or {}
        return ToolSpec(
            name=raw["name"],
            group=raw.get("group", ""),
            kind=raw.get("kind", "code"),
            description=raw["description"],
            input_model=None,  # YAML cannot reference Python types
            output_model=None,
            _input_schema=raw.get("input_schema"),
            _output_schema=raw.get("output_schema"),
            policy=policy,
            execution=execution,
            binding=binding,
            metadata=raw.get("metadata") or {},
            on_success_clear=tuple(contract_raw.get("on_success_clear", ())),
            on_success_reset=tuple(contract_raw.get("on_success_reset", ())),
            merge_strategy=contract_raw.get("merge_strategy", "reuse"),
            emit_artifact=contract_raw.get("emit_artifact", False),
        )
    except Exception as exc:
        logger.error("Failed to validate tool spec '%s': %s", raw.get("name", "?"), exc)
        return None


def load_tool_specs_from_source(source) -> list[dict[str, Any]]:
    """Discover raw tool dicts from a source.

    Returns the raw dicts — handler resolution happens in ToolRegistry.load_all().
    """
    return source.discover()
