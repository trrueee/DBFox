from __future__ import annotations

import uuid
from typing import Any

from engine.agent.answer import sanitize_answer_for_skipped_execution, synthesize_agent_answer
from engine.agent.artifacts import (
    AgentArtifactIdentity,
    build_agent_artifacts,
    build_error_artifact,
    build_recommendations_artifact,
)
from engine.agent.context import build_response_context_summary, referenced_artifact_ids
from engine.agent.events import build_trace_events
from engine.agent.narration import build_message_blocks, build_visible_events
from engine.agent.validation import validate_agent_response_contract
from engine.agent.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    AnswerEvidence,
    FollowUpSuggestion,
    ResultProfile,
)


class AgentKernelResponseAssembler:
    def build_response(
        self,
        *,
        req: AgentRunRequest,
        success: bool,
        steps: list[AgentStep],
        query_plan: dict[str, Any] | None,
        sql: str | None,
        safety: dict[str, Any] | None,
        execution: dict[str, Any] | None,
        explanation: str | None,
        chart_suggestion: dict[str, Any] | None,
        result_profile: dict[str, Any] | None,
        answer: dict[str, Any] | None,
        suggestions: list[dict[str, Any]],
        error: str | None,
        run_id: str | None = None,
        session_id: str | None = None,
        artifacts: list[AgentArtifact] | None = None,
        artifact_identity: AgentArtifactIdentity | None = None,
        status: str | None = None,
        approval: AgentApprovalRecord | None = None,
        checkpoint: AgentCheckpointRecord | None = None,
    ) -> AgentRunResponse:
        parsed_profile = ResultProfile.model_validate(result_profile) if result_profile else None
        parsed_suggestions = [
            FollowUpSuggestion.model_validate(item)
            for item in suggestions
            if isinstance(item, dict)
        ]
        parsed_answer = AgentAnswer.model_validate(answer) if answer else None
        if parsed_answer is None and (error or success):
            parsed_answer = synthesize_agent_answer(
                question=req.question,
                query_plan=query_plan,
                sql=sql,
                safety=safety,
                execution=execution,
                result_profile=parsed_profile,
                suggestions=parsed_suggestions,
                error=error,
            )
            explanation = explanation or parsed_answer.answer

        # Deterministic sanitizer: strip data-result claims when execution was skipped
        parsed_answer = sanitize_answer_for_skipped_execution(
            parsed_answer, execution, sql=sql, safety=safety,
        )

        # SQL-plan consistency: if query_plan specifies order_by but generated SQL
        # has no ORDER BY (e.g. LLM controller re-planned after sql generation),
        # inject the missing ORDER BY clause.
        sql = _inject_missing_order_by(sql, query_plan)

        response_artifacts = self._response_artifacts(
            artifacts=artifacts,
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            chart_suggestion=chart_suggestion,
            result_profile=parsed_profile,
            answer=parsed_answer,
            error=error,
            run_id=run_id,
            artifact_identity=artifact_identity,
        )
        if parsed_answer is not None:
            self._bind_answer_evidence(parsed_answer, response_artifacts)

        events = build_visible_events(
            question=req.question,
            steps=steps,
            artifacts=response_artifacts,
            answer=parsed_answer,
            suggestions=parsed_suggestions,
            error=error,
        )
        message_blocks = build_message_blocks(events)
        response_context_summary = build_response_context_summary(
            req=req,
            answer=parsed_answer.answer if parsed_answer else explanation,
            artifacts=response_artifacts,
        )

        response = AgentRunResponse(
            run_id=run_id or str(uuid.uuid4()),
            session_id=session_id or self._session_id(req),
            parent_run_id=req.parent_run_id or (req.follow_up_context.parent_run_id if req.follow_up_context else None),
            success=success,
            status=status or ("success" if success else "failed"),
            question=req.question,
            context_summary=response_context_summary,
            referenced_artifact_ids=referenced_artifact_ids(req),
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            explanation=explanation,
            chart_suggestion=chart_suggestion,
            result_profile=parsed_profile,
            answer=parsed_answer,
            suggestions=parsed_suggestions,
            artifacts=response_artifacts,
            message_blocks=message_blocks,
            events=events,
            trace_events=build_trace_events(steps),
            steps=steps,
            error=error,
            approval=approval,
            checkpoint=checkpoint,
        )
        validate_agent_response_contract(response)
        return response

    def _response_artifacts(
        self,
        *,
        artifacts: list[AgentArtifact] | None,
        query_plan: dict[str, Any] | None,
        sql: str | None,
        safety: dict[str, Any] | None,
        execution: dict[str, Any] | None,
        chart_suggestion: dict[str, Any] | None,
        result_profile: ResultProfile | None,
        answer: AgentAnswer | None,
        error: str | None,
        run_id: str | None,
        artifact_identity: AgentArtifactIdentity | None,
    ) -> list[AgentArtifact]:
        identity = artifact_identity or AgentArtifactIdentity(run_id)
        if artifacts is None:
            response_artifacts = build_agent_artifacts(
                query_plan=query_plan,
                sql=sql,
                safety=safety,
                execution=execution,
                chart_suggestion=chart_suggestion,
                result_profile=result_profile,
                answer=answer,
                error=error,
                identity=identity,
            )
        else:
            response_artifacts = list(artifacts)
            semantic_ids = {artifact.semantic_id or artifact.id for artifact in response_artifacts}
            if answer and answer.recommendations and "recommendations" not in semantic_ids:
                response_artifacts.append(build_recommendations_artifact(answer, identity=identity))
                semantic_ids.add("recommendations")
            if error and "agent_error" not in semantic_ids:
                response_artifacts.append(
                    build_error_artifact(error, safety=safety, execution=execution, identity=identity)
                )

        self._bind_artifact_dependencies(response_artifacts)
        return response_artifacts

    def _bind_answer_evidence(self, answer: AgentAnswer, artifacts: list[AgentArtifact]) -> None:
        semantic_to_id = {artifact.semantic_id or artifact.id: artifact.id for artifact in artifacts}
        artifact_ids = {artifact.id for artifact in artifacts}
        answer.evidence = [
            evidence
            for evidence in (
                evidence
                if evidence.artifact_id in artifact_ids
                else evidence.model_copy(update={"artifact_id": semantic_to_id.get(evidence.artifact_id, evidence.artifact_id)})
                for evidence in answer.evidence
            )
            if evidence.artifact_id in artifact_ids
        ]
        if not answer.evidence and artifacts:
            preferred_artifact = self._preferred_evidence_artifact(artifacts)
            answer.evidence = [
                AnswerEvidence(
                    artifact_id=preferred_artifact.id,
                    label=preferred_artifact.title,
                    value=preferred_artifact.summary if hasattr(preferred_artifact, "summary") else preferred_artifact.type,
                )
            ]

    def _preferred_evidence_artifact(self, artifacts: list[AgentArtifact]) -> AgentArtifact:
        preferred_semantic_ids = ("result_profile", "result_table", "safety_report", "sql_candidate", "query_plan")
        by_semantic_id = {artifact.semantic_id: artifact for artifact in artifacts if artifact.semantic_id}
        for semantic_id in preferred_semantic_ids:
            artifact = by_semantic_id.get(semantic_id)
            if artifact is not None:
                return artifact
        return artifacts[0]

    def _bind_artifact_dependencies(self, artifacts: list[AgentArtifact]) -> None:
        semantic_to_id = {artifact.semantic_id or artifact.id: artifact.id for artifact in artifacts}
        artifact_ids = {artifact.id for artifact in artifacts}
        for artifact in artifacts:
            dependencies = artifact.depends_on
            if artifact.type == "recommendation":
                dependencies = self._recommendation_dependency_keys(dependencies, semantic_to_id, artifact_ids)
            artifact.depends_on = [semantic_to_id.get(dependency, dependency) for dependency in dependencies]

    def _recommendation_dependency_keys(
        self,
        dependencies: list[str],
        semantic_to_id: dict[str, str],
        artifact_ids: set[str],
    ) -> list[str]:
        existing_dependencies = [
            dependency
            for dependency in dependencies
            if dependency in semantic_to_id or dependency in artifact_ids
        ]
        if existing_dependencies:
            return existing_dependencies

        for semantic_id in ("result_profile", "result_table", "sql_candidate", "safety_report"):
            if semantic_id in semantic_to_id:
                return [semantic_id]
        return []

    def _session_id(self, req: AgentRunRequest) -> str:
        if req.session_id:
            return req.session_id
        if req.follow_up_context and req.follow_up_context.session_id:
            return req.follow_up_context.session_id
        return str(uuid.uuid4())


def _inject_missing_order_by(sql: str | None, query_plan: dict[str, Any] | None) -> str | None:
    """If *query_plan* specifies an order_by but *sql* has no ORDER BY clause,
    parse the order_by value and inject it before LIMIT (or at end).
    Returns the (possibly modified) SQL.
    """
    if not sql or not query_plan:
        return sql
    raw: dict[str, Any] = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan  # type: ignore[assignment]
    ob = raw.get("order_by")
    if not ob:
        return sql
    if __import__("re").search(r"\bORDER\s+BY\b", sql, __import__("re").IGNORECASE):
        return sql

    # Extract column + direction from order_by value (supports repr/JSON/native)
    col, direction = _extract_order_by_col_dir(ob)
    if not col:
        return sql

    clause = f"{col} {direction}"
    m = __import__("re").search(r"\bLIMIT\s+\d+", sql, __import__("re").IGNORECASE)
    if m:
        idx = m.start()
        return f"{sql[:idx].rstrip()} ORDER BY {clause} {sql[idx:].lstrip()}"
    return f"{sql.rstrip().rstrip(';')} ORDER BY {clause}"


def _extract_order_by_col_dir(value: Any) -> tuple[str | None, str]:
    """Parse *value* (repr string, JSON string, or native list/dict/string)
    and return (column, direction).  direction defaults to 'ASC'.
    """
    # Parse if string
    if isinstance(value, str):
        stripped = value.strip()
        # JSON
        try:
            parsed = __import__("json").loads(stripped)
            if isinstance(parsed, (list, dict)):
                value = parsed
        except Exception:
            pass
        # Python repr
        if isinstance(value, str):
            try:
                parsed = __import__("ast").literal_eval(stripped)
                if isinstance(parsed, (list, dict)):
                    value = parsed
            except Exception:
                pass

    item: Any = None
    if isinstance(value, list):
        item = value[0] if value else None
    elif isinstance(value, dict):
        item = value
    elif isinstance(value, str):
        # plain string like "Age DESC"
        m = __import__("re").match(r"^(.+?)\s+(ASC|DESC)$", value.strip(), __import__("re").IGNORECASE)
        if m:
            return m.group(1).strip(), m.group(2).strip().upper()
        return value.strip(), "ASC"
    else:
        return None, "ASC"

    if isinstance(item, dict):
        col = str(item.get("column") or "").strip() or None
        direction = str(item.get("direction") or "ASC").strip().upper()
        if direction not in ("ASC", "DESC"):
            direction = "ASC"
        return col, direction

    return None, "ASC"
