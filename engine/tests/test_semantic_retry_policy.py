from __future__ import annotations

from engine.sql.semantics.contract import QueryContract
from engine.sql.semantics.retry import accept_semantic_retry, should_retry_semantic
from engine.sql.semantics.verifier import SemanticViolation


def test_semantic_retry_policy_requires_api_key_and_high_confidence_contract() -> None:
    violations = [
        SemanticViolation(
            code="having_missing",
            severity="retryable",
            message="HAVING is required.",
        )
    ]

    assert should_retry_semantic(QueryContract(confidence=0.75), violations, "TEST_LLM_SECRET") is True
    assert should_retry_semantic(QueryContract(confidence=0.75), violations, None) is False
    assert should_retry_semantic(QueryContract(confidence=0.5), violations, "TEST_LLM_SECRET") is False


def test_semantic_retry_policy_accepts_projection_only_improvement() -> None:
    contract = QueryContract(confidence=0.75)
    original = [
        {"code": "projection_extra_columns", "severity": "retryable"},
        {"code": "projection_duplicate_alias", "severity": "retryable"},
    ]
    retry = [{"code": "projection_duplicate_alias", "severity": "warning"}]

    assert accept_semantic_retry(
        original,
        retry,
        contract,
        original_sql="SELECT id, name, age FROM users WHERE country = 'US' LIMIT 100",
        retry_sql="SELECT id, name FROM users WHERE country = 'US' LIMIT 100",
    ) is True


def test_semantic_retry_policy_rejects_projection_topology_change() -> None:
    contract = QueryContract(confidence=0.75)
    original = [{"code": "projection_extra_columns", "severity": "retryable"}]
    retry = []

    assert accept_semantic_retry(
        original,
        retry,
        contract,
        original_sql="SELECT id, name FROM users WHERE country = 'US' LIMIT 100",
        retry_sql="SELECT id, name FROM users WHERE country = 'CN' LIMIT 100",
    ) is False
