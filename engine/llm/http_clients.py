"""Application-owned HTTP transports for LLM providers.

OpenAI's default client follows redirects.  That is unsuitable for a client
that carries a vault-resolved bearer credential, because a redirect can leave
the endpoint that passed the LLM URL policy.  These clients are shared for the
process lifetime and closed from the FastAPI lifespan.
"""
from __future__ import annotations

import threading

import httpx

from engine.llm.endpoint_policy import ResolvedLlmEndpoint


def _authority(host: str, port: int, scheme: str) -> str:
    rendered_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    default_port = 443 if scheme == "https" else 80
    return rendered_host if port == default_port else f"{rendered_host}:{port}"


class _PinnedEndpointTransport:
    """Rewrite only the socket target, preserving Host and TLS hostname checks."""

    def __init__(self, endpoint: ResolvedLlmEndpoint) -> None:
        if not endpoint.addresses:
            raise ValueError("A resolved LLM endpoint requires at least one address.")
        self._endpoint = endpoint
        # Address selection is intentionally fixed for the lifetime of this
        # transport. Re-resolving the hostname during a credential-bearing
        # request would defeat the policy admission that created it.
        self._pinned_address = endpoint.addresses[0]

    def _pin_request(self, request: httpx.Request) -> httpx.Request:
        request_host = str(request.url.host or "").rstrip(".").lower()
        request_scheme = str(request.url.scheme).lower()
        request_port = request.url.port or (443 if request_scheme == "https" else 80)
        if (
            request_scheme != self._endpoint.scheme
            or request_host != self._endpoint.host
            or request_port != self._endpoint.port
        ):
            raise httpx.RequestError(
                "LLM transport refused an unapproved request target.",
                request=request,
            )

        headers = request.headers.copy()
        headers["Host"] = _authority(
            self._endpoint.host,
            self._endpoint.port,
            self._endpoint.scheme,
        )
        extensions = dict(request.extensions)
        # httpcore passes this to SSLContext.wrap_socket as server_hostname,
        # retaining both SNI routing and certificate validation against the
        # configured hostname while the TCP connection uses the pinned IP.
        extensions["sni_hostname"] = self._endpoint.host
        return httpx.Request(
            request.method,
            request.url.copy_with(host=self._pinned_address),
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )


class _PinnedSyncTransport(_PinnedEndpointTransport, httpx.HTTPTransport):
    def __init__(self, endpoint: ResolvedLlmEndpoint) -> None:
        _PinnedEndpointTransport.__init__(self, endpoint)
        httpx.HTTPTransport.__init__(self, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.HTTPTransport.handle_request(self, self._pin_request(request))


class _PinnedAsyncTransport(_PinnedEndpointTransport, httpx.AsyncHTTPTransport):
    def __init__(self, endpoint: ResolvedLlmEndpoint) -> None:
        _PinnedEndpointTransport.__init__(self, endpoint)
        httpx.AsyncHTTPTransport.__init__(self, trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await httpx.AsyncHTTPTransport.handle_async_request(self, self._pin_request(request))


class LlmHttpTransportRegistry:
    """Own bounded, no-redirect HTTP clients keyed by endpoint and timeout."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sync_clients: dict[tuple[str, float], httpx.Client] = {}
        self._async_clients: dict[tuple[str, float], httpx.AsyncClient] = {}

    def get_clients(
        self,
        *,
        endpoint: ResolvedLlmEndpoint,
        timeout: float,
    ) -> tuple[httpx.Client, httpx.AsyncClient]:
        key = (endpoint.api_base, float(timeout))
        with self._lock:
            sync_client = self._sync_clients.get(key)
            if sync_client is None or sync_client.is_closed:
                sync_client = httpx.Client(
                    base_url=endpoint.api_base,
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=_PinnedSyncTransport(endpoint),
                )
                self._sync_clients[key] = sync_client

            async_client = self._async_clients.get(key)
            if async_client is None or async_client.is_closed:
                async_client = httpx.AsyncClient(
                    base_url=endpoint.api_base,
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=_PinnedAsyncTransport(endpoint),
                )
                self._async_clients[key] = async_client
            return sync_client, async_client

    async def aclose(self) -> None:
        with self._lock:
            sync_clients = tuple(self._sync_clients.values())
            async_clients = tuple(self._async_clients.values())
            self._sync_clients.clear()
            self._async_clients.clear()

        for sync_client in sync_clients:
            sync_client.close()
        for async_client in async_clients:
            await async_client.aclose()


_LLM_HTTP_TRANSPORTS = LlmHttpTransportRegistry()


def get_llm_http_clients(
    *,
    endpoint: ResolvedLlmEndpoint,
    timeout: float,
) -> tuple[httpx.Client, httpx.AsyncClient]:
    """Return application-owned clients after endpoint policy validation."""

    return _LLM_HTTP_TRANSPORTS.get_clients(endpoint=endpoint, timeout=timeout)


async def close_llm_http_clients() -> None:
    """Release all provider transports during application shutdown."""

    await _LLM_HTTP_TRANSPORTS.aclose()
