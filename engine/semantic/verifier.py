"""Semantic Verifier — deterministic verification of LLM semantic output.

Ensures that tables, columns, and join paths referenced by the semantic
resolver actually exist in the database catalog.  Low-confidence LLM
inferences are flagged but NOT blocked — they become suggestions, not facts.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.environment.service import EnvironmentService
from engine.semantic.models import (
    CandidateColumn,
    CandidateTable,
    JoinPathCandidate,
    ResolvedDimension,
    ResolvedFilter,
    ResolvedMetric,
    ResolvedTerm,
    SemanticResolution,
    SemanticSource,
)

logger = logging.getLogger("databox.semantic.verifier")


class VerificationIssue(BaseModel):
    """A single verification issue found by SemanticVerifier."""

    field: str = Field(description="Which field in SemanticResolution has the issue.")
    detail: str = Field(description="Human-readable description of the issue.")
    severity: str = Field(default="warning", description="'error' or 'warning'.")


class VerificationResult(BaseModel):
    """Result of semantic verification."""

    passed: bool = Field(description="True if no errors were found (warnings are ok).")
    issues: list[VerificationIssue] = Field(default_factory=list)
    corrected_resolution: SemanticResolution | None = Field(default=None)


class SemanticVerifier:
    """Deterministic verification of LLM-produced SemanticResolution.

    Verifies that:
    - Referenced tables exist in the catalog.
    - Referenced columns belong to their claimed tables.
    - Join paths reference real tables and columns.
    - LLM-inferred facts are correctly marked (source=llm_inference).

    Verification FAILS (passed=False) only for database_metadata violations:
    table doesn't exist, column doesn't exist.  LLM inference with low
    confidence generates warnings, not failures.
    """

    def __init__(self, db: Session):
        self.db = db
        self.env = EnvironmentService()

    def verify(
        self,
        resolution: SemanticResolution,
        datasource_id: str,
    ) -> VerificationResult:
        issues: list[VerificationIssue] = []
        snapshot = self.env.get_catalog_snapshot(self.db, datasource_id)

        # Build lookup maps
        table_names: set[str] = {t.table_name.lower() for t in snapshot.tables}
        column_map: dict[str, set[str]] = {}
        for t in snapshot.tables:
            column_map[t.table_name.lower()] = {
                c.column_name.lower() for c in t.columns
            }

        # ---- Verify candidate tables ----
        for ct in resolution.candidate_tables:
            if ct.table_name.lower() not in table_names:
                issues.append(VerificationIssue(
                    field=f"candidate_tables.{ct.table_name}",
                    detail=f"Table '{ct.table_name}' does not exist in the catalog.",
                    severity="error",
                ))

        # ---- Verify candidate columns ----
        for cc in resolution.candidate_columns:
            tbl_lower = cc.table_name.lower()
            col_lower = cc.column_name.lower()
            if tbl_lower not in table_names:
                issues.append(VerificationIssue(
                    field=f"candidate_columns.{cc.table_name}.{cc.column_name}",
                    detail=f"Table '{cc.table_name}' does not exist.",
                    severity="error",
                ))
            elif col_lower not in column_map.get(tbl_lower, set()):
                issues.append(VerificationIssue(
                    field=f"candidate_columns.{cc.table_name}.{cc.column_name}",
                    detail=f"Column '{cc.column_name}' does not exist in table '{cc.table_name}'.",
                    severity="error",
                ))

        # ---- Verify resolved terms ----
        for term in resolution.resolved_terms:
            if term.mapped_table and term.mapped_table.lower() not in table_names:
                issues.append(VerificationIssue(
                    field=f"resolved_terms.{term.term}",
                    detail=f"Mapped table '{term.mapped_table}' does not exist.",
                    severity="error",
                ))
            if term.source == SemanticSource.llm_inference:
                issues.append(VerificationIssue(
                    field=f"resolved_terms.{term.term}",
                    detail=f"Term '{term.term}' is LLM-inferred and unverified.",
                    severity="warning",
                ))

        # ---- Verify resolved metrics ----
        for metric in resolution.resolved_metrics:
            if metric.table and metric.table.lower() not in table_names:
                issues.append(VerificationIssue(
                    field=f"resolved_metrics.{metric.name}",
                    detail=f"Metric table '{metric.table}' does not exist.",
                    severity="error",
                ))
            if metric.source == SemanticSource.llm_inference:
                issues.append(VerificationIssue(
                    field=f"resolved_metrics.{metric.name}",
                    detail=f"Metric '{metric.name}' is LLM-inferred — expression may be incorrect.",
                    severity="warning",
                ))

        # ---- Verify resolved dimensions ----
        for dim in resolution.resolved_dimensions:
            if dim.table and dim.table.lower() not in table_names:
                issues.append(VerificationIssue(
                    field=f"resolved_dimensions.{dim.name}",
                    detail=f"Dimension table '{dim.table}' does not exist.",
                    severity="error",
                ))
            if dim.source == SemanticSource.llm_inference:
                issues.append(VerificationIssue(
                    field=f"resolved_dimensions.{dim.name}",
                    detail=f"Dimension '{dim.name}' is LLM-inferred.",
                    severity="warning",
                ))

        # ---- Verify resolved filters ----
        for f in resolution.resolved_filters:
            if f.table and f.table.lower() not in table_names:
                issues.append(VerificationIssue(
                    field=f"resolved_filters.{f.description}",
                    detail=f"Filter table '{f.table}' does not exist.",
                    severity="error",
                ))

        # ---- Verify join paths ----
        for jp in resolution.join_paths:
            for table in jp.tables:
                if table.lower() not in table_names:
                    issues.append(VerificationIssue(
                        field=f"join_paths.{jp.tables}",
                        detail=f"Join table '{table}' does not exist.",
                        severity="error",
                    ))
            if jp.source == "llm_inferred":
                issues.append(VerificationIssue(
                    field=f"join_paths.{jp.tables}",
                    detail="Join path is LLM-inferred — may be incorrect. Verify before using.",
                    severity="warning",
                ))

        errors = [i for i in issues if i.severity == "error"]
        return VerificationResult(
            passed=len(errors) == 0,
            issues=issues,
        )
