"""ASGI request-body limits for endpoints that persist user-supplied payloads."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


MAX_AGENT_INPUT_REQUEST_BYTES = 512 * 1024


class AgentInputRequestBodyLimitMiddleware:
    """Reject oversized Agent input bodies before JSON parsing or persistence."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_AGENT_INPUT_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if not self._is_limited_request(scope):
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        buffered: list[Message] = []
        received = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") == "http.request":
                received += len(message.get("body") or b"")
                if received > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message.get("type") == "http.disconnect":
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _is_limited_request(scope: Scope) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        parts = str(scope.get("path") or "").strip("/").split("/")
        return (
            len(parts) == 5
            and parts[:3] == ["api", "v1", "conversations"]
            and parts[4] == "inputs"
        ) or parts == ["api", "v1", "agent", "console", "execute"]

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for raw_name, raw_value in scope.get("headers") or []:
            if raw_name.lower() != b"content-length":
                continue
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                return None
        return None

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": {
                    "code": "REQUEST_BODY_TOO_LARGE",
                    "message": "Agent request body exceeds the allowed size.",
                }
            },
        )
        await response(scope, receive, send)
