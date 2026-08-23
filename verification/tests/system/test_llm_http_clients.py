from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from engine.llm.endpoint_policy import ResolvedLlmEndpoint
from engine.llm.http_clients import LlmHttpTransportRegistry, _PinnedSyncTransport


def _endpoint() -> ResolvedLlmEndpoint:
    return ResolvedLlmEndpoint(
        api_base="https://api.example.test/v1",
        scheme="https",
        host="api.example.test",
        port=443,
        addresses=("8.8.8.8",),
    )


def test_llm_http_clients_are_reused_without_redirects_or_environment_proxy() -> None:
    registry = LlmHttpTransportRegistry()

    sync_client, async_client = registry.get_clients(
        endpoint=_endpoint(),
        timeout=12.0,
    )
    same_sync, same_async = registry.get_clients(
        endpoint=_endpoint(),
        timeout=12.0,
    )

    assert same_sync is sync_client
    assert same_async is async_client
    assert sync_client.follow_redirects is False
    assert async_client.follow_redirects is False
    assert sync_client.trust_env is False
    assert async_client.trust_env is False

    asyncio.run(registry.aclose())
    assert sync_client.is_closed is True
    assert async_client.is_closed is True


def test_pinned_transport_uses_admitted_ip_and_preserves_tls_hostname() -> None:
    transport = _PinnedSyncTransport(_endpoint())
    try:
        pinned = transport._pin_request(
            httpx.Request("POST", "https://api.example.test/v1/chat/completions", content=b"{}")
        )
    finally:
        transport.close()

    assert pinned.url.host == "8.8.8.8"
    assert pinned.headers["host"] == "api.example.test"
    assert pinned.extensions["sni_hostname"] == "api.example.test"


def test_pinned_transport_rejects_a_request_to_another_origin() -> None:
    transport = _PinnedSyncTransport(_endpoint())
    try:
        with pytest.raises(httpx.RequestError):
            transport._pin_request(httpx.Request("GET", "https://other.example.test/v1"))
    finally:
        transport.close()


def test_pinned_transport_connects_to_the_admitted_address_without_re_resolving() -> None:
    received: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            received["host"] = self.headers.get("Host")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = int(server.server_address[1])
    endpoint = ResolvedLlmEndpoint(
        api_base=f"http://localhost:{port}/v1",
        scheme="http",
        host="localhost",
        port=port,
        addresses=("127.0.0.1",),
    )
    registry = LlmHttpTransportRegistry()
    try:
        client, _async_client = registry.get_clients(endpoint=endpoint, timeout=5.0)
        response = client.get("/health")
        assert response.status_code == 200
        assert received["host"] == f"localhost:{port}"
    finally:
        asyncio.run(registry.aclose())
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
