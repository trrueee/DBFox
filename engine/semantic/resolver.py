"""Semantic Resolver — LLM structured output + deterministic verifier.

Maps user business language to database objects using the Environment layer
for ground truth and an LLM for semantic understanding.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from engine.environment.service import EnvironmentService
from engine.llm import get_chat_model
from engine.semantic.models import SemanticResolution
from engine.semantic.prompts import SEMANTIC_RESOLVER_PROMPT
from engine.semantic.verifier import SemanticVerifier

logger = logging.getLogger("dbfox.semantic.resolver")


class SemanticResolver:
    """Resolve user business language into structured semantic objects.

    Combines LLM understanding with deterministic catalog verification.
    """

    def __init__(self, db: Session):
        self.db = db
        self.env = EnvironmentService()
        self.verifier = SemanticVerifier(db)

    def resolve(
        self,
        question: str,
        datasource_id: str,
        *,
        workspace_context: dict[str, Any] | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> SemanticResolution:
        """Resolve business semantics for a user question.

        Args:
            question: The user's natural language question.
            datasource_id: The datasource to resolve against.
            workspace_context: Optional workspace context for additional hints.
            model_name: LLM model override.
            api_key: LLM API key override.
            api_base: LLM API base URL override.

        Returns:
            SemanticResolution with verified tables/columns/terms/metrics/dimensions.
        """
        # 1. Gather environment facts
        profile = self.env.get_profile(self.db, datasource_id)
        snapshot = self.env.get_catalog_snapshot(self.db, datasource_id)

        # 2. Build the resolution prompt with catalog context
        catalog_summary = self._catalog_summary(snapshot)
        workspace_summary = self._workspace_summary(workspace_context)

        user_prompt = (
            f"## User Question\n{question}\n\n"
            f"## Environment\n"
            f"dialect={profile.dialect}, env={profile.env}, "
            f"catalog_status={profile.catalog_status}, tables={profile.table_count}\n"
        )
        if workspace_summary:
            user_prompt += f"\n## Workspace Context\n{workspace_summary}\n"
        user_prompt += f"\n## Available Catalog\n{catalog_summary}"

        # 3. Call LLM with structured output
        try:
            model = get_chat_model(
                model_name=model_name,
                api_key=api_key,
                api_base=api_base,
            )
            structured_model = model.with_structured_output(SemanticResolution)
            resolution = structured_model.invoke([
                {"role": "system", "content": SEMANTIC_RESOLVER_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
        except Exception as exc:
            logger.error("SemanticResolver LLM call failed: %s", exc)
            return SemanticResolution(
                user_goal=question,
                task_shape="unknown",
                confidence="low",
                missing_information=[f"LLM resolution failed: {exc}"],
                semantic_context_text=f"Unable to resolve semantics. Error: {exc}",
            )

        # 4. Deterministic verification
        verification = self.verifier.verify(resolution, datasource_id)
        if verification.corrected_resolution:
            resolution = verification.corrected_resolution

        if not verification.passed:
            error_details = [i.detail for i in verification.issues if i.severity == "error"]
            logger.warning(
                "Semantic verification found %d errors: %s",
                len(error_details),
                error_details[:5],
            )
            resolution.missing_information.extend(error_details)

        # 5. Build semantic_context_text if the LLM didn't produce one
        if not resolution.semantic_context_text:
            resolution.semantic_context_text = self._render_context_text(resolution)

        return resolution

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _catalog_summary(snapshot) -> str:
        """Build a compact catalog summary for the LLM prompt."""
        lines = []
        for t in snapshot.tables[:30]:  # Cap at 30 tables to avoid prompt bloat
            cols = [c.column_name for c in t.columns[:20]]
            fks = [
                r for r in (snapshot.relationships or [])
                if hasattr(r, 'column_name') and any(
                    c.column_name == r.column_name for c in t.columns
                )
            ]
            fk_str = ""
            if fks:
                fk_refs = [f"{r.column_name} → {r.referenced_table}.{r.referenced_column}" for r in fks]
                fk_str = f"  FK: {', '.join(fk_refs)}"
            lines.append(
                f"  {t.table_name} ({t.column_count} cols): {', '.join(cols[:15])}{fk_str}"
            )
        if len(snapshot.tables) > 30:
            lines.append(f"  ... and {len(snapshot.tables) - 30} more tables.")
        return "\n".join(lines) if lines else "(empty catalog)"

    @staticmethod
    def _workspace_summary(workspace: dict[str, Any] | None) -> str:
        """Build a compact workspace summary."""
        if not workspace:
            return ""
        parts = []
        active_sql = workspace.get("active_sql") or workspace.get("selected_sql")
        if active_sql:
            parts.append(f"Active SQL: {str(active_sql)[:200]}")
        selected_tables = workspace.get("selected_table_names") or []
        if selected_tables:
            parts.append(f"Selected tables: {', '.join(selected_tables)}")
        return "\n".join(parts)

    @staticmethod
    def _render_context_text(resolution: SemanticResolution) -> str:
        """Render a compact semantic context text block."""
        lines = [f"Goal: {resolution.user_goal}"]

        if resolution.resolved_terms:
            terms = [f"{t.term} → {t.mapped_expression or t.mapped_column or t.mapped_table or 'unresolved'}"
                     for t in resolution.resolved_terms[:8]]
            lines.append(f"Terms: {'; '.join(terms)}")

        if resolution.resolved_metrics:
            metrics = [f"{m.name}={m.expression or m.column or '?'}" for m in resolution.resolved_metrics[:5]]
            lines.append(f"Metrics: {'; '.join(metrics)}")

        if resolution.resolved_dimensions:
            dims = [f"{d.name}({d.grain or '?'})" for d in resolution.resolved_dimensions[:5]]
            lines.append(f"Dimensions: {'; '.join(dims)}")

        if resolution.join_paths:
            joins = [" + ".join(j.tables) for j in resolution.join_paths[:3]]
            lines.append(f"Joins: {'; '.join(joins)}")

        if resolution.ambiguity:
            lines.append(f"Ambiguity: {'; '.join(a.description for a in resolution.ambiguity[:3])}")

        return "\n".join(lines)
