from __future__ import annotations

import socket

import pytest

from engine.llm.config import LlmConfigurationError, resolve_product_llm_config_from_credential
from engine.llm.endpoint_policy import (
    LlmEndpointPolicyError,
    normalize_llm_api_base,
    resolve_runtime_llm_endpoint,
    validate_runtime_llm_api_base,
)
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def _resolver(*_args, **_kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ]


def test_public_https_endpoint_is_normalized_and_validated(monkeypatch) -> None:
    monkeypatch.setattr("engine.llm.endpoint_policy.socket.getaddrinfo", _resolver)

    assert normalize_llm_api_base(" HTTPS://api.example.test/v1 ") == "https://api.example.test/v1"
    assert validate_runtime_llm_api_base("https://api.example.test/v1") == "https://api.example.test/v1"
    endpoint = resolve_runtime_llm_endpoint("https://api.example.test/v1")
    assert endpoint.host == "api.example.test"
    assert endpoint.addresses == ("8.8.8.8",)


@pytest.mark.parametrize(
    "api_base",
    [
        "http://api.example.test/v1",
        "https://user:password@api.example.test/v1",
        "https://api.example.test/v1?target=internal",
        "https://api.example.test/v1#fragment",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "file:///tmp/llm",
    ],
)
def test_unsafe_or_ambiguous_endpoint_is_rejected_before_secret_resolution(api_base: str) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="policy-sentinel")

    with pytest.raises(LlmConfigurationError) as exc_info:
        resolve_product_llm_config_from_credential(
            llm_credential_id=credential_id,
            api_base=api_base,
            model_name="model",
            credential_vault=vault,
        )

    assert exc_info.value.code == "LLM_ENDPOINT_NOT_ALLOWED"
    assert "policy-sentinel" not in str(exc_info.value)


def test_runtime_validation_rejects_public_hostname_resolving_to_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.llm.endpoint_policy.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
    )

    with pytest.raises(LlmEndpointPolicyError) as exc_info:
        validate_runtime_llm_api_base("https://api.example.test/v1")

    assert exc_info.value.code == "LLM_ENDPOINT_NOT_ALLOWED"


def test_loopback_http_requires_an_explicit_development_switch(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.llm.endpoint_policy.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 11434)),
        ],
    )
    monkeypatch.delenv("DBFOX_ALLOW_LOOPBACK_LLM_HTTP", raising=False)

    with pytest.raises(LlmEndpointPolicyError):
        validate_runtime_llm_api_base("http://localhost:11434/v1")

    monkeypatch.setenv("DBFOX_ALLOW_LOOPBACK_LLM_HTTP", "1")
    assert validate_runtime_llm_api_base("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_loopback_http_never_accepts_a_non_loopback_resolution(monkeypatch) -> None:
    monkeypatch.setenv("DBFOX_ALLOW_LOOPBACK_LLM_HTTP", "1")
    monkeypatch.setattr(
        "engine.llm.endpoint_policy.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.30", 11434)),
        ],
    )

    with pytest.raises(LlmEndpointPolicyError):
        validate_runtime_llm_api_base("http://localhost:11434/v1")
