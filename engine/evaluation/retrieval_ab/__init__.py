"""Retrieval A/B/n evaluation framework for DBFox."""

from engine.evaluation.retrieval_ab.config import RetrievalAbConfig
from engine.evaluation.retrieval_ab.metrics import (
    CaseEvaluationInput,
    CaseEvaluationResult,
    ExpectedSchema,
    RetrievalHit,
    VariantSummary,
    evaluate_case,
    extract_expected_schema_from_sql,
    summarize_variant,
)
from engine.evaluation.retrieval_ab.variants import SUPPORTED_VARIANTS, fuse_rrf

__all__ = [
    "CaseEvaluationInput",
    "CaseEvaluationResult",
    "ExpectedSchema",
    "RetrievalAbConfig",
    "RetrievalHit",
    "SUPPORTED_VARIANTS",
    "VariantSummary",
    "evaluate_case",
    "extract_expected_schema_from_sql",
    "fuse_rrf",
    "summarize_variant",
]
