"""Network policy for OpenAI-compatible LLM endpoints.

The renderer and Agent Runtime can select a provider endpoint, but neither is a
network-security boundary.  This module is the single place that decides
whether resolving a vault-held credential for an endpoint is permitted.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit


class LlmEndpointPolicyError(ValueError):
    """Raised when an LLM endpoint could send a credential to an unsafe host."""

    def __init__(self, message: str = "LLM endpoint is not allowed.") -> None:
        super().__init__(message)
        self.code = "LLM_ENDPOINT_NOT_ALLOWED"


@dataclass(frozen=True)
class ResolvedLlmEndpoint:
    """A policy-approved endpoint bound to the addresses resolved for this client."""

    api_base: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _parsed_endpoint(value: str | None) -> SplitResult:
    raw = str(value or "").strip()
    if not raw or len(raw) > 2048:
        raise LlmEndpointPolicyError()

    try:
        parsed = urlsplit(raw)
        # Accessing .port validates malformed and out-of-range port values.
        parsed_port = parsed.port
    except ValueError as exc:
        raise LlmEndpointPolicyError() from exc

    if parsed_port == 0:
        raise LlmEndpointPolicyError()

    host = parsed.hostname
    if (
        parsed.scheme.lower() not in {"https", "http"}
        or not parsed.netloc
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.netloc
    ):
        raise LlmEndpointPolicyError()
    return parsed


def _is_loopback_literal(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.rstrip(".").lower() == "localhost"


def _is_non_public_literal(host: str) -> bool:
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _allow_loopback_http() -> bool:
    return os.environ.get("DBFOX_ALLOW_LOOPBACK_LLM_HTTP") == "1"


def normalize_llm_api_base(value: str | None) -> str:
    """Validate URL syntax before a vault secret is resolved.

    Remote endpoints are HTTPS-only.  Plain HTTP is intentionally a narrowly
    scoped development escape hatch for a loopback endpoint and additionally
    requires a process-local opt-in.  DNS/IP verification happens immediately
    before client creation, when the address will actually be used.
    """

    parsed = _parsed_endpoint(value)
    scheme = parsed.scheme.lower()
    host = str(parsed.hostname)
    if scheme == "http":
        if not _allow_loopback_http() or not _is_loopback_literal(host):
            raise LlmEndpointPolicyError()
    elif _is_non_public_literal(host) or host.rstrip(".").lower() == "localhost":
        raise LlmEndpointPolicyError()

    return urlunsplit((scheme, parsed.netloc, parsed.path or "/", "", ""))


def _resolved_addresses(host: str, port: int) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise LlmEndpointPolicyError() from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        except (IndexError, ValueError):
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise LlmEndpointPolicyError()
    return tuple(addresses)


def resolve_runtime_llm_endpoint(value: str | None) -> ResolvedLlmEndpoint:
    """Resolve and bind an endpoint before a credential-bearing client is built.

    The provider calls this directly before creating a client, so callers that
    construct ``LlmConfig`` manually cannot bypass DNS/IP policy.  Redirects
    are not part of the endpoint contract.  Consumers must use ``addresses``
    as the actual transport target while retaining ``host`` for HTTP Host and
    TLS SNI/certificate validation; reconnecting by hostname would re-open a
    DNS-rebinding window after this admission check.
    """

    normalized = normalize_llm_api_base(value)
    parsed = _parsed_endpoint(normalized)
    host = str(parsed.hostname)
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    addresses = _resolved_addresses(host, port)

    if parsed.scheme.lower() == "http":
        if not _allow_loopback_http() or not all(address.is_loopback for address in addresses):
            raise LlmEndpointPolicyError()
    elif not all(address.is_global for address in addresses):
        raise LlmEndpointPolicyError()
    return ResolvedLlmEndpoint(
        api_base=normalized,
        scheme=parsed.scheme.lower(),
        host=host.rstrip(".").lower(),
        port=port,
        addresses=tuple(str(address) for address in addresses),
    )


def validate_runtime_llm_api_base(value: str | None) -> str:
    """Return the normalized API base for callers that do not own a transport."""

    return resolve_runtime_llm_endpoint(value).api_base
