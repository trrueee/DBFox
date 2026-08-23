from __future__ import annotations

from engine.main import LOCAL_SECURE_TOKEN, app


def test_unauthorized_response_is_correlated_problem_details(client) -> None:
    response = client.get("/api/v1/conversations", headers={"X-Local-Token": ""})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem == {
        "type": "urn:dbfox:problem:unauthorized-engine-access",
        "title": "Unauthorized",
        "status": 401,
        "detail": "A valid local engine token is required.",
        "instance": "/api/v1/conversations",
        "code": "UNAUTHORIZED_ENGINE_ACCESS",
        "request_id": response.headers["x-request-id"],
    }


def test_root_runtime_status_is_not_a_public_authentication_bypass(client) -> None:
    unauthenticated = client.get("/", headers={"X-Local-Token": ""})
    authenticated = client.get("/", headers={"X-Local-Token": LOCAL_SECURE_TOKEN})

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["status"] == "running"


def test_validation_problem_never_echoes_invalid_input(client) -> None:
    secret = "never-echo-this-password"
    response = client.post(
        "/api/v1/conversations",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
        json={"title": {"password": secret}},
    )

    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert problem["status"] == 422
    assert problem["errors"]
    assert secret not in response.text
    assert all(set(error) == {"location", "message", "error_type"} for error in problem["errors"])


def test_openapi_advertises_problem_details_media_type() -> None:
    responses = app.openapi()["paths"]["/api/v1/conversations"]["post"]["responses"]
    for status in (400, 401, 403, 404, 409, 422, 500, 503):
        response_contract = responses[str(status)]
        assert set(response_contract["content"]) == {"application/problem+json"}
        schema = response_contract["content"]["application/problem+json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ProblemDetails"}
    schema = app.openapi()["components"]["schemas"]["ProblemDetails"]
    assert {"type", "title", "status", "detail", "instance", "code", "request_id"}.issubset(
        schema["properties"]
    )
