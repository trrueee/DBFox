"""Fixed public-error and diagnostic catalogs for untrusted exceptions.

This module deliberately has no DBFox imports so low-level runtime modules can
use it without creating a dependency cycle.  Error boundaries may select only
catalog members; arbitrary exception text and caller-supplied log labels are
never rendered into public payloads or diagnostics.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from enum import Enum
from logging import Logger
from typing import Final, Literal


class FixedErrorCode(str, Enum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RESULT_PAGE_ERROR = "RESULT_PAGE_ERROR"
    RESULT_EXPORT_ERROR = "RESULT_EXPORT_ERROR"
    AGENT_REQUEST_ERROR = "AGENT_REQUEST_ERROR"
    AGENT_RUNTIME_ERROR = "AGENT_RUNTIME_ERROR"
    AGENT_CONTEXT_UNAVAILABLE = "AGENT_CONTEXT_UNAVAILABLE"
    AGENT_CANCELLED = "AGENT_CANCELLED"
    AGENT_LEASE_LOST = "AGENT_LEASE_LOST"
    AGENT_USAGE_UNAVAILABLE = "AGENT_USAGE_UNAVAILABLE"
    AGENT_TOKEN_BUDGET = "AGENT_TOKEN_BUDGET"
    AGENT_COST_PRICING_UNAVAILABLE = "AGENT_COST_PRICING_UNAVAILABLE"
    AGENT_COST_BUDGET = "AGENT_COST_BUDGET"
    AGENT_PROVIDER_RETRY_BUDGET = "AGENT_PROVIDER_RETRY_BUDGET"
    AGENT_REPAIR_BUDGET = "AGENT_REPAIR_BUDGET"
    AGENT_DEADLINE_EXCEEDED = "AGENT_DEADLINE_EXCEEDED"
    AGENT_INCOMPLETE = "AGENT_INCOMPLETE"
    AGENT_TURN_BUDGET = "AGENT_TURN_BUDGET"
    AGENT_TOOL_BUDGET = "AGENT_TOOL_BUDGET"
    AGENT_NO_PROGRESS = "AGENT_NO_PROGRESS"
    AGENT_QUESTION_EXPIRED = "AGENT_QUESTION_EXPIRED"
    TOOL_INPUT_ERROR = "TOOL_INPUT_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AGENT_INPUT_INVALID = "AGENT_INPUT_INVALID"
    NO_LLM_CREDENTIAL = "NO_LLM_CREDENTIAL"
    LLM_CONFIG_ERROR = "LLM_CONFIG_ERROR"
    LLM_CREDENTIAL_NOT_FOUND = "LLM_CREDENTIAL_NOT_FOUND"
    LLM_ENDPOINT_NOT_ALLOWED = "LLM_ENDPOINT_NOT_ALLOWED"
    CREDENTIAL_VAULT_UNAVAILABLE = "CREDENTIAL_VAULT_UNAVAILABLE"
    MODEL_PROVIDER_TIMEOUT = "MODEL_PROVIDER_TIMEOUT"
    MODEL_PROVIDER_REQUEST_TIMEOUT = "MODEL_PROVIDER_REQUEST_TIMEOUT"
    MODEL_PROVIDER_FIRST_EVENT_TIMEOUT = "MODEL_PROVIDER_FIRST_EVENT_TIMEOUT"
    MODEL_PROVIDER_STREAM_IDLE_TIMEOUT = "MODEL_PROVIDER_STREAM_IDLE_TIMEOUT"
    MODEL_PROVIDER_TURN_TIMEOUT = "MODEL_PROVIDER_TURN_TIMEOUT"
    MODEL_PROVIDER_UNAVAILABLE = "MODEL_PROVIDER_UNAVAILABLE"
    MODEL_PROVIDER_RATE_LIMITED = "MODEL_PROVIDER_RATE_LIMITED"
    MODEL_PROVIDER_QUOTA_EXCEEDED = "MODEL_PROVIDER_QUOTA_EXCEEDED"
    MODEL_PROVIDER_AUTHENTICATION_FAILED = "MODEL_PROVIDER_AUTHENTICATION_FAILED"
    MODEL_PROVIDER_PERMISSION_DENIED = "MODEL_PROVIDER_PERMISSION_DENIED"
    MODEL_PROVIDER_MODEL_NOT_FOUND = "MODEL_PROVIDER_MODEL_NOT_FOUND"
    MODEL_PROVIDER_REQUEST_REJECTED = "MODEL_PROVIDER_REQUEST_REJECTED"
    MODEL_PROVIDER_PROTOCOL_ERROR = "MODEL_PROVIDER_PROTOCOL_ERROR"
    MODEL_PROVIDER_STREAM_FAILED = "MODEL_PROVIDER_STREAM_FAILED"
    MODEL_PROVIDER_STREAM_TRUNCATED = "MODEL_PROVIDER_STREAM_TRUNCATED"
    MODEL_PROVIDER_INCOMPLETE = "MODEL_PROVIDER_INCOMPLETE"
    MODEL_PROVIDER_FAILED = "MODEL_PROVIDER_FAILED"


_FIXED_ERROR_MESSAGES: Final[dict[FixedErrorCode, str]] = {
    FixedErrorCode.INTERNAL_ERROR: "The request could not be completed.",
    FixedErrorCode.NOT_FOUND: "The requested resource was not found.",
    FixedErrorCode.RESULT_PAGE_ERROR: "The Artifact page could not be retrieved.",
    FixedErrorCode.RESULT_EXPORT_ERROR: "The Artifact export could not be generated.",
    FixedErrorCode.AGENT_REQUEST_ERROR: "The agent request could not be completed.",
    FixedErrorCode.AGENT_RUNTIME_ERROR: "The agent run could not be completed.",
    FixedErrorCode.AGENT_CONTEXT_UNAVAILABLE: "Agent context is temporarily unavailable.",
    FixedErrorCode.AGENT_CANCELLED: "分析已取消。",
    FixedErrorCode.AGENT_LEASE_LOST: "分析执行权已转移。",
    FixedErrorCode.AGENT_USAGE_UNAVAILABLE: "模型未返回可核算的用量信息。",
    FixedErrorCode.AGENT_TOKEN_BUDGET: "分析已达到本次 Token 预算。",
    FixedErrorCode.AGENT_COST_PRICING_UNAVAILABLE: "当前模型未配置可核算价格。",
    FixedErrorCode.AGENT_COST_BUDGET: "分析已达到本次费用预算。",
    FixedErrorCode.AGENT_PROVIDER_RETRY_BUDGET: "模型服务连续失败，已停止重试。",
    FixedErrorCode.AGENT_REPAIR_BUDGET: "分析修复次数已达到上限。",
    FixedErrorCode.AGENT_DEADLINE_EXCEEDED: "分析已达到本次运行时限。",
    FixedErrorCode.AGENT_INCOMPLETE: "模型未能完成当前分析。",
    FixedErrorCode.AGENT_TURN_BUDGET: "分析已达到轮次上限。",
    FixedErrorCode.AGENT_TOOL_BUDGET: "工具调用已达到本次分析上限。",
    FixedErrorCode.AGENT_NO_PROGRESS: "连续多轮没有产生新的可验证结果，已停止重复尝试。",
    FixedErrorCode.AGENT_QUESTION_EXPIRED: "等待补充信息已超时，请重新发起分析。",
    FixedErrorCode.TOOL_INPUT_ERROR: "The tool input is invalid.",
    FixedErrorCode.VALIDATION_FAILED: "The request did not satisfy the required validation rules.",
    FixedErrorCode.AGENT_INPUT_INVALID: "输入无效，请检查必填字段。",
    FixedErrorCode.NO_LLM_CREDENTIAL: "请先在设置中配置模型凭据。",
    FixedErrorCode.LLM_CONFIG_ERROR: "模型配置无效，请检查模型设置。",
    FixedErrorCode.LLM_CREDENTIAL_NOT_FOUND: "模型凭据已不可用，请在设置中重新选择或保存凭据。",
    FixedErrorCode.LLM_ENDPOINT_NOT_ALLOWED: "不允许连接该模型服务地址，请检查端点配置。",
    FixedErrorCode.CREDENTIAL_VAULT_UNAVAILABLE: "The credential vault is unavailable.",
    FixedErrorCode.MODEL_PROVIDER_TIMEOUT: "模型服务响应超时。",
    FixedErrorCode.MODEL_PROVIDER_REQUEST_TIMEOUT: "模型服务未及时接受请求。",
    FixedErrorCode.MODEL_PROVIDER_FIRST_EVENT_TIMEOUT: "模型服务未及时开始响应。",
    FixedErrorCode.MODEL_PROVIDER_STREAM_IDLE_TIMEOUT: "模型服务响应流长时间没有进展。",
    FixedErrorCode.MODEL_PROVIDER_TURN_TIMEOUT: "本轮模型处理已达到时限。",
    FixedErrorCode.MODEL_PROVIDER_UNAVAILABLE: "模型服务暂时不可用，请稍后重试。",
    FixedErrorCode.MODEL_PROVIDER_RATE_LIMITED: "模型服务请求过于频繁，请稍后重试。",
    FixedErrorCode.MODEL_PROVIDER_QUOTA_EXCEEDED: "模型服务额度或账单限制已阻止请求，请检查账户额度。",
    FixedErrorCode.MODEL_PROVIDER_AUTHENTICATION_FAILED: "模型服务鉴权失败，请检查凭据。",
    FixedErrorCode.MODEL_PROVIDER_PERMISSION_DENIED: "当前凭据无权使用所选模型或模型服务。",
    FixedErrorCode.MODEL_PROVIDER_MODEL_NOT_FOUND: "未找到所选模型或模型服务地址，请检查配置。",
    FixedErrorCode.MODEL_PROVIDER_REQUEST_REJECTED: "模型服务拒绝了当前请求，请检查模型和参数配置。",
    FixedErrorCode.MODEL_PROVIDER_PROTOCOL_ERROR: "模型服务返回了无法识别的响应。",
    FixedErrorCode.MODEL_PROVIDER_STREAM_FAILED: "模型服务调用失败。",
    FixedErrorCode.MODEL_PROVIDER_STREAM_TRUNCATED: "模型响应在完成前意外中断。",
    FixedErrorCode.MODEL_PROVIDER_INCOMPLETE: "模型未能完成当前响应。",
    FixedErrorCode.MODEL_PROVIDER_FAILED: "模型服务未能完成当前响应。",
}


class SafeLogOperation(str, Enum):
    UNEXPECTED = "unexpected_internal_error"
    AGENT_MODEL_PROVIDER_STREAM = "agent_model_provider_stream"
    AGENT_RESULT_PAGE = "agent_result_page"
    AGENT_RESULT_EXPORT = "agent_result_export"
    TOOL_RUNTIME_INPUT_CONTRACT_FAILED = "tool_runtime_tool_input_contract_failed"
    TOOL_RUNTIME_OUTPUT_CONTRACT_FAILED = "tool_runtime_tool_output_contract_failed"
    TOOL_RUNTIME_EXECUTION_FAILED = "tool_runtime_tool_execution_failed"


def _safe_error_code(code: object) -> FixedErrorCode:
    if isinstance(code, FixedErrorCode):
        return code
    candidate = code.value if isinstance(code, Enum) else code
    try:
        return FixedErrorCode(str(candidate))
    except (TypeError, ValueError):
        return FixedErrorCode.INTERNAL_ERROR


def fixed_error_detail(code: object) -> dict[str, str]:
    """Return a cataloged public error without accepting arbitrary text."""
    safe_code = _safe_error_code(code)
    return {"code": safe_code.value, "message": _FIXED_ERROR_MESSAGES[safe_code]}


def fixed_error_message(code: object) -> str:
    """Return only the fixed message for a catalog member."""
    return fixed_error_detail(code)["message"]


_DIAGNOSTIC_FINGERPRINT_KEY: Final[bytes] = secrets.token_bytes(32)


def diagnostic_fingerprint(value: object) -> str:
    """Return an opaque, process-scoped correlation fingerprint.

    Sensitive diagnostics are intentionally keyed with process-local entropy
    instead of a plain digest.  This permits correlation inside one running
    process without making low-entropy SQL literals or exception text
    guessable from diagnostic logs after the process exits.
    """
    try:
        payload = value if isinstance(value, bytes) else str(value).encode("utf-8", "replace")
    except Exception:
        payload = type(value).__name__.encode("utf-8")
    return hmac.new(_DIAGNOSTIC_FINGERPRINT_KEY, payload, hashlib.sha256).hexdigest()[:24]


def log_sensitive_diagnostic(
    logger: Logger,
    *,
    operation: SafeLogOperation,
    subject: object,
    subject_type: Literal["sql", "exception", "event"],
    level: Literal["warning", "error"] = "warning",
) -> None:
    """Log a cataloged diagnostic without rendering SQL or exception text."""
    safe_operation = operation if isinstance(operation, SafeLogOperation) else SafeLogOperation.UNEXPECTED
    log = logger.warning if level == "warning" else logger.error
    log(
        "code=%s type=%s fingerprint=%s",
        safe_operation.value,
        subject_type,
        diagnostic_fingerprint(subject),
    )


_EXTENSION_DIAGNOSTIC_OPERATION = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*){2,7}$"
)


def _safe_extension_diagnostic_operation(operation: str) -> str:
    candidate = str(operation).strip()
    return (
        candidate
        if len(candidate) <= 128 and _EXTENSION_DIAGNOSTIC_OPERATION.fullmatch(candidate)
        else "extension.unexpected.operation"
    )


def log_extension_diagnostic(
    logger: Logger,
    *,
    operation: str,
    subject: object,
    subject_type: Literal["sql", "exception", "event"],
    level: Literal["warning", "error"] = "warning",
) -> None:
    """Log a namespaced DLC diagnostic without rendering sensitive content."""

    safe_operation = _safe_extension_diagnostic_operation(operation)
    log = logger.warning if level == "warning" else logger.error
    log(
        "code=%s type=%s fingerprint=%s",
        safe_operation,
        subject_type,
        diagnostic_fingerprint(subject),
    )


def log_extension_exception(
    logger: Logger,
    *,
    operation: str,
    exc: Exception,
    fingerprint_subject: object | None = None,
    level: Literal["warning", "error"] = "error",
) -> None:
    """Log a DLC exception type and opaque fingerprint without its message."""

    safe_operation = _safe_extension_diagnostic_operation(operation)
    log = logger.warning if level == "warning" else logger.error
    log(
        "code=%s type=%s fingerprint=%s",
        safe_operation,
        type(exc).__name__,
        diagnostic_fingerprint(
            exc if fingerprint_subject is None else fingerprint_subject
        ),
    )


def log_unexpected_exception(
    logger: Logger,
    *,
    operation: SafeLogOperation,
    exc: Exception,
    fingerprint_subject: object | None = None,
    level: Literal["warning", "error"] = "error",
) -> None:
    """Log a cataloged error code, exception type, and opaque fingerprint only."""
    safe_operation = operation if isinstance(operation, SafeLogOperation) else SafeLogOperation.UNEXPECTED
    log = logger.warning if level == "warning" else logger.error
    log(
        "code=%s type=%s fingerprint=%s",
        safe_operation.value,
        type(exc).__name__,
        diagnostic_fingerprint(exc if fingerprint_subject is None else fingerprint_subject),
    )
