"""DBFox Policy Layer — safety guardrails and policy enforcement.

Modules:
  engine       — PolicyEngine (rule-based policy enforcement)
  redactor     — DataRedactor (sensitive data masking)
  confirmation — Confirmation manager for destructive operations
  gate         — PolicyGate (tool-level safety gate for agent)

Note: SQL safety enforcement lives in engine.sql.guardrail (sqlglot AST),
and approval / tool-argument gating is handled dynamically by PolicyGate.
"""

from engine.policy.engine import PolicyEngine
from engine.policy.redactor import DataRedactor
from engine.policy.confirmation import confirmation_manager, confirmation_bypass_enabled, sha256_hash
from engine.policy.gate import PolicyGate, PolicyDecision

__all__ = [
    "PolicyEngine",
    "DataRedactor",
    "confirmation_manager",
    "confirmation_bypass_enabled",
    "sha256_hash",
    "PolicyGate",
    "PolicyDecision",
]
