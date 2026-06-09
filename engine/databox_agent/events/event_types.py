from __future__ import annotations

# Event type constants used in SSE streaming and runtime event records.
# Mirrors engine.agent.types.AgentRuntimeEventType for backward compatibility.

RUN_STARTED = "agent.run.started"
MODEL_STARTED = "agent.model.started"
MODEL_COMPLETED = "agent.model.completed"
TOOL_CALL_REQUESTED = "agent.tool_call.requested"
STEP_STARTED = "agent.step.started"
STEP_COMPLETED = "agent.step.completed"
POLICY_ALLOWED = "agent.policy.allowed"
POLICY_BLOCKED = "agent.policy.blocked"
APPROVAL_REQUIRED = "agent.approval.required"
APPROVAL_RESOLVED = "agent.approval.resolved"
TOOL_STARTED = "agent.tool.started"
TOOL_COMPLETED = "agent.tool.completed"
OBSERVE_APPLIED = "agent.observe.applied"
ARTIFACT_CREATED = "agent.artifact.created"
ANSWER_COMPLETED = "agent.answer.completed"
FINALIZED = "agent.finalized"
RUN_COMPLETED = "agent.run.completed"
RUN_FAILED = "agent.run.failed"
CHECKPOINT_SAVED = "agent.checkpoint.saved"
RUN_WAITING_APPROVAL = "agent.run.waiting_approval"
RUN_RESUMED = "agent.run.resumed"
