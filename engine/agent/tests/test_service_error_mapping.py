from __future__ import annotations


def test_runtime_llm_timeout_error_is_user_facing():
    from engine.agent.app.service import _runtime_error_message

    message = _runtime_error_message(TimeoutError("Request timed out."))

    assert message == "LLM 响应超时，请检查模型服务网络、API Base 与模型可用性后重试。"


def test_runtime_non_llm_error_keeps_internal_context():
    from engine.agent.app.service import _runtime_error_message

    message = _runtime_error_message(RuntimeError("stream boom"))

    assert message == "Internal agent error: stream boom"
