from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from engine.app.request_limits import AgentInputRequestBodyLimitMiddleware


def _test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AgentInputRequestBodyLimitMiddleware, max_bytes=8)

    @app.post("/api/v1/conversations/{conversation_id}/inputs")
    async def conversation_input(conversation_id: str, request: Request) -> dict[str, str]:
        await request.body()
        return {"conversation_id": conversation_id}

    @app.post("/api/v1/unrelated")
    async def unrelated(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return app


def test_agent_input_routes_reject_oversized_bodies() -> None:
    with TestClient(_test_app()) as client:
        for path in ("/api/v1/conversations/session_1/inputs",):
            response = client.post(path, content=b"123456789")
            assert response.status_code == 413
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["code"] == "REQUEST_BODY_TOO_LARGE"


def test_unrelated_routes_are_not_claimed_by_agent_input_limit() -> None:
    with TestClient(_test_app()) as client:
        response = client.post("/api/v1/unrelated", content=b"123456789")
        assert response.status_code == 200
        assert response.json() == {"size": 9}
