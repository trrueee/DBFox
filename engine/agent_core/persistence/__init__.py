"""DBFox Agent persistence layer — facade re-exports.

All public symbols are re-exported here so that existing consumers
using ``from engine.agent_core import persistence as ap`` or
``from engine.agent_core.persistence import X`` continue to work unchanged.
"""
from engine.agent_core.persistence._common import (
    _safe_json,
    _parse_json_any,
    _parse_json,
    _SENSITIVE_KEYS,
    _safe_event_payload,
    _redact_trace_for_storage,
    _redact_trace_event,
    _normalize_risk_level,
    _approval_record,
    _checkpoint_record,
    _restore_response,
    _redact_response,
    _load_run_artifacts,
    _artifact_to_dict,
    _summarize_artifact_payload,
    _to_timestamp_ms,
    _format_cell,
)
from engine.agent_core.persistence.sessions import create_or_get_session
from engine.agent_core.persistence.runs import (
    start_run,
    complete_run,
    fail_run,
    cancel_run,
    mark_run_waiting_approval,
    mark_run_resumed,
    get_run,
    list_session_runs,
    get_recent_run,
    get_run_sequence_by_session,
    build_followup_context_from_run,
)
from engine.agent_core.persistence.events import (
    record_runtime_event,
    record_artifact,
    get_latest_runtime_event_sequence,
    list_run_artifacts,
    list_run_events,
    list_run_trace_events,
    restore_artifact,
    restore_runtime_event,
)
from engine.agent_core.persistence.approvals import (
    create_approval,
    get_approval,
    get_pending_approval_for_run,
    list_run_approvals,
    resolve_approval,
    expire_approval,
)
from engine.agent_core.persistence.checkpoints import (
    save_checkpoint,
    get_latest_checkpoint,
    get_latest_checkpoint_payload,
    list_checkpoints,
)
from engine.agent_core.persistence.conversation_records import (
    get_conversation_detail,
    list_conversation_summaries,
    serialize_artifact,
    serialize_message,
    serialize_run,
)
__all__ = [
    # _common
    "_safe_json", "_parse_json_any", "_parse_json", "_SENSITIVE_KEYS",
    "_safe_event_payload", "_redact_trace_for_storage", "_redact_trace_event",
    "_normalize_risk_level", "_approval_record", "_checkpoint_record",
    "_restore_response", "_redact_response", "_load_run_artifacts",
    "_artifact_to_dict", "_summarize_artifact_payload", "_to_timestamp_ms",
    "_format_cell",
    # sessions
    "create_or_get_session",
    # runs
    "start_run", "complete_run", "fail_run", "cancel_run",
    "mark_run_waiting_approval", "mark_run_resumed",
    "get_run", "list_session_runs", "get_recent_run",
    "get_run_sequence_by_session", "build_followup_context_from_run",
    # events
    "record_runtime_event", "record_artifact",
    "get_latest_runtime_event_sequence",
    "list_run_artifacts", "list_run_events", "list_run_trace_events",
    "restore_artifact", "restore_runtime_event",
    # approvals
    "create_approval", "get_approval", "get_pending_approval_for_run",
    "list_run_approvals", "resolve_approval", "expire_approval",
    # checkpoints
    "save_checkpoint", "get_latest_checkpoint",
    "get_latest_checkpoint_payload", "list_checkpoints",
    # conversation records
    "get_conversation_detail", "list_conversation_summaries",
    "serialize_artifact", "serialize_message", "serialize_run",
]
