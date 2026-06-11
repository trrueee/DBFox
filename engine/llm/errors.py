from __future__ import annotations

from engine.errors import DataBoxError


def llm_error_from_exception(exc: Exception) -> DataBoxError | None:
    """Map provider/client exceptions to stable UI-facing LLM errors."""
    text = str(exc)
    lower_text = text.lower()
    class_name = exc.__class__.__name__.lower()
    combined = f"{class_name} {lower_text}"

    if any(marker in combined for marker in (
        "authentication",
        "invalid_api_key",
        "incorrect api key",
        "unauthorized",
        "error code: 401",
        "status code: 401",
    )):
        return DataBoxError(
            "LLM API Key 校验失败，请检查 API Key、API Base 与模型服务权限。",
            code="LLM_AUTH_ERROR",
        )

    if any(marker in combined for marker in (
        "ratelimit",
        "rate_limit",
        "rate limit",
        "error code: 429",
        "status code: 429",
    )):
        return DataBoxError(
            "LLM 服务触发限流，请稍后重试或检查模型服务配额。",
            code="LLM_RATE_LIMIT",
        )

    if any(marker in combined for marker in (
        "timeout",
        "timed out",
        "readtimeout",
        "apitimeouterror",
    )):
        return DataBoxError(
            "LLM 响应超时，请检查模型服务网络、API Base 与模型可用性后重试。",
            code="LLM_TIMEOUT",
        )

    if any(marker in combined for marker in (
        "apiconnectionerror",
        "connection error",
        "connection refused",
        "network",
        "name resolution",
        "dns",
    )):
        return DataBoxError(
            "无法连接到 LLM 服务，请检查网络、API Base 或代理配置。",
            code="LLM_CONNECTION_ERROR",
        )

    if any(marker in combined for marker in (
        "model_not_found",
        "model not found",
        "error code: 404",
        "status code: 404",
    )):
        return DataBoxError(
            "LLM 模型不可用，请检查模型名称是否正确并确认账号有访问权限。",
            code="LLM_MODEL_ERROR",
        )

    if any(marker in combined for marker in (
        "badrequest",
        "bad request",
        "error code: 400",
        "status code: 400",
    )):
        return DataBoxError(
            "LLM 请求参数不被模型服务接受，请检查模型名称、API Base 与请求配置。",
            code="LLM_REQUEST_ERROR",
        )

    return None
