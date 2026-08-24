"""Opt-in dbfox.data suite runner over the production DBFox Agent Harness."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from verification.bench.capabilities.dbfox_data.agent.reporting import TrialRecord
from verification.bench.capabilities.dbfox_data.agent.schema import (
    DatasetManifest,
    EvalCase,
)
from verification.bench.capabilities.dbfox_data.agent.scoring import (
    PlanTrace,
    ResultTable,
    RunTrace,
    ToolTrace,
    TrialTrace,
    TurnEfficiencyTrace,
    score_trial,
)


class EvaluationConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealProviderIdentity:
    model: str
    api_base: str
    credential_reference: str


def _mask(value: str) -> str:
    if len(value) <= 12:
        return "configured"
    return f"{value[:6]}…{value[-4:]}"


def configure_isolated_runtime(runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=False)
    metadata = runtime_dir / "metadata.sqlite"
    os.environ["DBFOX_RUNTIME_DIR"] = str(runtime_dir)
    os.environ["DBFOX_DATABASE_URL"] = f"sqlite:///{metadata.as_posix()}"
    return metadata


def seed_sqlite_database(path: Path, seed_file: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(seed_file.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def _query_table(
    database: Path,
    sql: str,
    parameters: dict[str, Any] | list[Any] | tuple[Any, ...] | None = None,
    *,
    max_rows: int = 2_000,
) -> ResultTable:
    value = sql.strip()
    if not (value.lower().startswith("select") or value.lower().startswith("with")):
        raise ValueError("Data CapabilityBench only executes read-only result queries")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        cursor = connection.execute(value, parameters or {})
        columns = tuple(str(item[0]) for item in (cursor.description or ()))
        rows = tuple(tuple(row) for row in cursor.fetchmany(max_rows + 1))
        if len(rows) > max_rows:
            raise ValueError("Data CapabilityBench result exceeded the bounded scorer row limit")
        return ResultTable(columns=columns, rows=rows)
    finally:
        connection.close()


def _snapshot_checks(database: Path, statements: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    for statement in statements:
        result = _query_table(database, statement)
        encoded = json.dumps(
            result.model_dump(mode="json"), sort_keys=True, default=str
        )
        values[statement] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return values


def _optional_parameters(value: Any) -> dict[str, Any] | list[Any] | None:
    """Narrow persisted JSON to the parameter shapes sqlite accepts."""

    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    return None


def _non_negative_int(value: Any) -> int:
    """Read an optional persisted counter without trusting arbitrary JSON."""

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
    return 0


def _optional_non_negative_int(value: Any) -> int | None:
    return None if value is None else _non_negative_int(value)


def _usage_int(usage: dict[str, Any], primary: str, fallback: str) -> int:
    return _non_negative_int(usage.get(primary, usage.get(fallback, 0)))


def _duration_ms(started_at: Any, completed_at: Any) -> float:
    if started_at is None or completed_at is None:
        return 0.0
    return max(0.0, (completed_at - started_at).total_seconds() * 1000)


def _select_generated_query(
    artifacts: list[Any],
    answer: str,
    load_object: Any,
    citation_references: Any,
) -> tuple[str | None, dict[str, Any] | list[Any] | None]:
    """Resolve the first answer-cited result to its authoritative SQL artifact."""

    by_id = {str(item.id): item for item in artifacts}
    sql_artifacts = [item for item in artifacts if str(item.type) == "sql"]
    selected_sql = sql_artifacts[-1] if sql_artifacts else None
    for artifact_id, _start, _end in citation_references(answer):
        result_artifact = by_id.get(artifact_id)
        if result_artifact is None or str(result_artifact.type) != "result_view":
            continue
        result_payload = load_object(str(result_artifact.payload_json or "{}"))
        source_id = str(result_payload.get("sourceSqlArtifactId") or "").strip()
        source_artifact = by_id.get(source_id)
        if source_artifact is not None and str(source_artifact.type) == "sql":
            selected_sql = source_artifact
            break
    if selected_sql is None:
        return None, None
    payload = load_object(str(selected_sql.payload_json or "{}"))
    generated_sql = str(payload.get("safeSql") or "").strip() or None
    return generated_sql, _optional_parameters(payload.get("parameters"))


def _plan_trace(plan: Any, events: list[Any], load_object: Any) -> PlanTrace:
    if plan is None:
        return PlanTrace()
    try:
        steps = json.loads(str(plan.steps_json or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        steps = []
    statuses = [
        str(step.get("status") or "") for step in steps if isinstance(step, dict)
    ]
    step_id_versions: list[tuple[str, ...]] = []
    for event in events:
        payload = load_object(str(event.payload_json or "{}"))
        item = payload.get("item") if isinstance(payload, dict) else None
        if not isinstance(item, dict) or item.get("type") != "plan":
            continue
        item_payload = item.get("payload")
        item_steps = (
            item_payload.get("steps") if isinstance(item_payload, dict) else None
        )
        if not isinstance(item_steps, list):
            continue
        step_id_versions.append(
            tuple(
                str(step.get("id"))
                for step in item_steps
                if isinstance(step, dict) and step.get("id")
            )
        )
    stable_step_ids = not step_id_versions or all(
        ids == step_id_versions[0] for ids in step_id_versions[1:]
    )
    return PlanTrace(
        exists=True,
        version_count=max(int(plan.version or 0), len(step_id_versions)),
        terminal_status=str(plan.status),
        step_count=len(statuses),
        completed_steps=statuses.count("completed"),
        skipped_steps=statuses.count("skipped"),
        blocked_steps=statuses.count("blocked"),
        pending_steps=statuses.count("pending"),
        in_progress_steps=statuses.count("in_progress"),
        stable_step_ids=stable_step_ids,
    )


def _resolve_provider_config():
    # Imports stay inside the function: engine.db binds DBFOX_DATABASE_URL at
    # module import time, after configure_isolated_runtime has fenced the run.
    from engine.llm.config import (
        DEFAULT_LLM_API_BASE,
        DEFAULT_LLM_MODEL_NAME,
        LlmConfig,
        resolve_product_llm_config_from_credential,
    )
    from engine.llm.endpoint_policy import normalize_llm_api_base

    credential_id = os.getenv("DBFOX_REAL_LLM_CREDENTIAL_ID", "").strip()
    api_base = os.getenv("DBFOX_REAL_LLM_API_BASE")
    model_name = os.getenv("DBFOX_REAL_LLM_MODEL")
    if credential_id:
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=credential_id,
            api_base=api_base,
            model_name=model_name,
        )
        return config, RealProviderIdentity(
            model=config.model_name,
            api_base=config.api_base,
            credential_reference=_mask(credential_id),
        )
    api_key = os.getenv("DBFOX_REAL_LLM_API_KEY", "").strip()
    if api_key and os.getenv("DBFOX_ALLOW_REAL_LLM_ENV_KEY") == "1":
        config = LlmConfig(
            api_key=api_key,
            api_base=normalize_llm_api_base(api_base or DEFAULT_LLM_API_BASE),
            model_name=(model_name or DEFAULT_LLM_MODEL_NAME).strip(),
            source="data-capability-bench-ci",
        )
        return config, RealProviderIdentity(
            model=config.model_name,
            api_base=config.api_base,
            credential_reference="ci-secret",
        )
    raise EvaluationConfigurationError(
        "Real Provider evaluation requires DBFOX_REAL_LLM_CREDENTIAL_ID, or an "
        "explicit test-only DBFOX_REAL_LLM_API_KEY gate."
    )


def _infrastructure_reason(status: str, error_code: str | None) -> str | None:
    if status == "runner_failed":
        return error_code or "runner_failed"
    code = str(error_code or "")
    if code.startswith("LLM_") or code in {
        "AGENT_PROVIDER_RETRY_BUDGET",
        "AGENT_COST_PRICING_UNAVAILABLE",
        "MODEL_PROVIDER_TIMEOUT",
        "MODEL_PROVIDER_UNAVAILABLE",
        "MODEL_PROVIDER_RATE_LIMITED",
        "MODEL_PROVIDER_QUOTA_EXCEEDED",
        "MODEL_PROVIDER_AUTHENTICATION_FAILED",
        "MODEL_PROVIDER_PERMISSION_DENIED",
        "MODEL_PROVIDER_MODEL_NOT_FOUND",
    }:
        return code
    return None



def run_real_provider(
    *,
    manifest: DatasetManifest,
    cases: tuple[EvalCase, ...],
    repetitions: int,
    work_dir: Path,
) -> tuple[tuple[TrialRecord, ...], RealProviderIdentity]:
    """Run natural-language tasks through the production RunLoop.

    The evaluator owns only dataset setup, trace collection and grading. Model
    turns, tool policy, SQL validation/execution, Artifacts and terminalization
    are the production implementations.
    """

    if os.getenv("DBFOX_RUN_REAL_LLM") != "1":
        raise EvaluationConfigurationError(
            "Set DBFOX_RUN_REAL_LLM=1 to acknowledge network use and model cost."
        )
    if not 1 <= repetitions <= 5:
        raise ValueError("repetitions must be between 1 and 5")

    metadata_path = configure_isolated_runtime(work_dir / "runtime")
    datasource_path = work_dir / "data-capability-bench.sqlite"
    seed_sqlite_database(
        datasource_path,
        Path(__file__).resolve().parent / "datasets" / "sqlite-seed-v1.sql",
    )
    config, identity = _resolve_provider_config()

    from engine.agent.completion import CompletionGate
    from engine.agent.events import LiveStreamHub
    from engine.agent.evidence import citation_references
    from engine.agent.loop import RunLoop
    from engine.agent.providers.openai import OpenAIModelAdapter
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.resource_refs import RequestedResourceRef
    from engine.dlc.api import DlcOperationContext
    from engine.runtime_composition import (
        authorize_project_resources,
        build_default_completion_policy,
        build_product_tool_registry,
        default_capability_guidance,
        default_context_contributors,
        initialize_runtime_snapshot,
    )
    from engine.db import (
        DATABASE_URL,
        SessionLocal,
        engine as runtime_metadata_engine,
        run_alembic_upgrade,
        verify_metadata_database,
    )
    from engine.json_codec import load_object
    from engine.models import (
        AgentArtifactRecord,
        AgentEventRecord,
        AgentMessage,
        AgentObservationRecord,
        AgentRun,
        AgentRunItemRecord,
        AgentTaskPlanRecord,
        AgentToolInvocation,
        AgentTurn,
        Project,
    )
    from scripts.prepare_dev_system_dlcs import prepare_dev_system_dlcs

    configured_metadata = Path(str(DATABASE_URL).replace("sqlite:///", "")).resolve()
    if configured_metadata != metadata_path.resolve():
        raise RuntimeError("Data CapabilityBench did not bind the isolated metadata database")
    run_alembic_upgrade(DATABASE_URL)
    verify_metadata_database(DATABASE_URL)

    system_dlc_dir, system_dlc_manifest = prepare_dev_system_dlcs()
    snapshot = initialize_runtime_snapshot(
        system_dlc_dir=system_dlc_dir,
        system_dlc_manifest=system_dlc_manifest,
    )
    project_id = f"data-capability-bench-{manifest.seed_version}"
    with SessionLocal() as db:
        db.add(Project(id=project_id, name=f"Data CapabilityBench {manifest.seed_version}"))
        db.commit()

    def invoke_data_operation(name: str, payload: dict[str, Any]) -> Any:
        contribution = snapshot.get_operation("dbfox.data", name)
        if contribution is None:
            raise RuntimeError(f"Production dbfox.data operation is unavailable: {name}")
        operation_input = contribution.spec.input_model.model_validate(payload)
        output = contribution.spec.handler(
            operation_input,
            DlcOperationContext(
                dlc_id="dbfox.data",
                operation_name=name,
                project_id=project_id,
            ),
        )
        return contribution.spec.output_model.model_validate(output)

    created_profile = invoke_data_operation(
        "profiles.create",
        {
            "name": "DBFox Data CapabilityBench Synthetic",
            "provider": "sqlite",
            "is_read_only": True,
            "environment": "test",
            "initial_database_name": str(datasource_path.resolve()),
            "initial_database_display_name": "Data CapabilityBench",
        },
    )
    database_id = str(created_profile.databases[0].id)
    invoke_data_operation("catalog.refresh", {"database_id": database_id})

    with SessionLocal() as db:
        resource_refs = authorize_project_resources(
            db,
            project_id,
            (RequestedResourceRef(kind="dbfox.data.database", id=database_id),),
            snapshot=snapshot,
        )
    if len(resource_refs) != 1:
        raise RuntimeError("Data CapabilityBench database authority was not frozen exactly once")
    session_factory = SessionLocal
    secret = str(getattr(config, "api_key", "") or "")

    def create_session(case: EvalCase, repetition: int) -> str:
        with session_factory() as db:
            aggregate = SessionRepository(db).create(
                project_id=project_id,
                title=f"[Data CapabilityBench] {case.case_id} r{repetition}",
            )
            if case.history:
                aggregate.message_sequence = len(case.history)
                for sequence, item in enumerate(case.history, start=1):
                    db.add(
                        AgentMessage(
                            session_id=str(aggregate.id),
                            role=item.role,
                            content=item.content,
                            status="completed",
                            sequence=sequence,
                        )
                    )
            db.commit()
            return str(aggregate.id)

    def execute_prompt(
        *,
        session_id: str,
        case: EvalCase,
        repetition: int,
        prompt_index: int,
    ) -> tuple[str, str]:
        with session_factory() as db:
            sessions = SessionRepository(db)
            admission = sessions.admit(
                session_id=session_id,
                resource_refs=resource_refs,
                content=case.prompts[prompt_index],
                idempotency_key=(
                    f"data-bench-{manifest.dataset_version}-{case.case_id}-"
                    f"{repetition}-{prompt_index}"
                ),
                llm_credential_id="data-bench-configured-provider",
                api_base=identity.api_base,
                model_name=identity.model,
                request_payload={
                    "evaluation_dataset": manifest.dataset_id,
                    "evaluation_case": case.case_id,
                },
            )
            lease = sessions.claim(
                session_id=session_id,
                owner="data-capability-bench",
                ttl_seconds=900,
            )
            if lease is None:
                raise RuntimeError("Data CapabilityBench could not claim the Session lease")
            sessions.promote_next_input(lease=lease)
            db.commit()

        loop.execute(lease=lease, run_id=admission.run_id)
        return admission.run_id, admission.assistant_message_id

    def collect(
        run_ids: list[str], answer_id: str, case: EvalCase
    ) -> tuple[TrialTrace, str | None]:
        with session_factory() as db:
            runs = [db.get(AgentRun, run_id) for run_id in run_ids]
            final_run = runs[-1] if runs else None
            answer = db.get(AgentMessage, answer_id) if answer_id else None
            tools = (
                db.query(AgentToolInvocation)
                .filter(AgentToolInvocation.run_id.in_(run_ids))
                .order_by(AgentToolInvocation.created_at, AgentToolInvocation.id)
                .all()
                if run_ids
                else []
            )
            artifacts = (
                db.query(AgentArtifactRecord)
                .filter(AgentArtifactRecord.run_id.in_(run_ids))
                .order_by(AgentArtifactRecord.created_at, AgentArtifactRecord.id)
                .all()
                if run_ids
                else []
            )
            turns = (
                db.query(AgentTurn)
                .filter(AgentTurn.run_id.in_(run_ids))
                .order_by(AgentTurn.created_at, AgentTurn.id)
                .all()
                if run_ids
                else []
            )
            observations = (
                db.query(AgentObservationRecord)
                .filter(AgentObservationRecord.run_id.in_(run_ids))
                .order_by(AgentObservationRecord.created_at, AgentObservationRecord.id)
                .all()
                if run_ids
                else []
            )
            run_items = (
                db.query(AgentRunItemRecord)
                .filter(AgentRunItemRecord.run_id.in_(run_ids))
                .order_by(AgentRunItemRecord.sequence, AgentRunItemRecord.id)
                .all()
                if run_ids
                else []
            )
            events = (
                db.query(AgentEventRecord)
                .filter(AgentEventRecord.run_id.in_(run_ids))
                .order_by(AgentEventRecord.sequence, AgentEventRecord.id)
                .all()
                if run_ids
                else []
            )
            plans = (
                db.query(AgentTaskPlanRecord)
                .filter(AgentTaskPlanRecord.run_id.in_(run_ids))
                .order_by(AgentTaskPlanRecord.updated_at, AgentTaskPlanRecord.id)
                .all()
                if run_ids
                else []
            )
            result_artifacts = [
                item for item in artifacts if str(item.type) == "result_view"
            ]
            query_fingerprints: list[str] = []
            for artifact in result_artifacts:
                payload = load_object(str(artifact.payload_json))
                fingerprint = str(payload.get("queryFingerprint") or "").strip()
                if fingerprint:
                    query_fingerprints.append(fingerprint)
            text = str(answer.content or "") if answer is not None else ""
            generated_sql, generated_parameters = _select_generated_query(
                artifacts,
                text,
                load_object,
                citation_references,
            )
            error_code = (
                str(final_run.error_code)
                if final_run and final_run.error_code
                else None
            )
            prompt_budgets = []
            turn_efficiency: list[TurnEfficiencyTrace] = []
            run_sequence_by_id = {
                str(run_id): sequence
                for sequence, run_id in enumerate(run_ids, start=1)
            }
            for turn in turns:
                snapshot = load_object(str(turn.context_snapshot_json or "{}"))
                budget = snapshot.get("prompt_budget")
                prompt_budget = budget if isinstance(budget, dict) else {}
                prompt_budgets.append(prompt_budget)
                usage = load_object(str(turn.usage_json or "{}"))
                turn_efficiency.append(
                    TurnEfficiencyTrace(
                        run_sequence=run_sequence_by_id.get(str(turn.run_id), 1),
                        turn_sequence=max(1, int(turn.sequence or 1)),
                        provider_input_tokens=_usage_int(
                            usage, "prompt_tokens", "input_tokens"
                        ),
                        provider_output_tokens=_usage_int(
                            usage, "completion_tokens", "output_tokens"
                        ),
                        cached_input_tokens=_optional_non_negative_int(
                            usage.get("cached_input_tokens")
                        ),
                        reasoning_output_tokens=_optional_non_negative_int(
                            usage.get("reasoning_output_tokens")
                        ),
                        estimated_prompt_tokens=_non_negative_int(
                            prompt_budget.get("estimated_prompt_tokens")
                        ),
                        max_prompt_tokens=_non_negative_int(
                            prompt_budget.get("max_prompt_tokens")
                        ),
                        message_tokens=_non_negative_int(
                            prompt_budget.get("message_tokens")
                        ),
                        reserved_tokens=_non_negative_int(
                            prompt_budget.get("reserved_tokens")
                        ),
                        tool_schema_count=_non_negative_int(
                            prompt_budget.get("tool_schema_count")
                        ),
                        tool_schema_tokens=_non_negative_int(
                            prompt_budget.get("tool_schema_tokens")
                        ),
                        response_item_tokens=_non_negative_int(
                            prompt_budget.get("response_item_tokens")
                        ),
                        evidence_ledger_tokens=_non_negative_int(
                            prompt_budget.get("evidence_ledger_tokens")
                        ),
                        consumed_steer_tokens=_non_negative_int(
                            prompt_budget.get("consumed_steer_tokens")
                        ),
                        omitted_messages=_non_negative_int(
                            prompt_budget.get("omitted_messages")
                        ),
                        truncated_messages=_non_negative_int(
                            prompt_budget.get("truncated_messages")
                        ),
                        omitted_response_items=_non_negative_int(
                            prompt_budget.get("omitted_response_items")
                        ),
                        omitted_response_batches=_non_negative_int(
                            prompt_budget.get("omitted_response_batches")
                        ),
                        transient_tool_output_count=_non_negative_int(
                            prompt_budget.get("transient_tool_output_count")
                        ),
                        transient_tool_output_bytes=_non_negative_int(
                            prompt_budget.get("transient_tool_output_bytes")
                        ),
                        tool_materialization_hash=str(
                            turn.tool_materialization_hash or ""
                        ),
                    )
                )
            durable_surfaces = [
                *(str(run.result_json or "") for run in runs if run),
                *(str(run.error_message or "") for run in runs if run),
                *(str(turn.reasoning_summary or "") for turn in turns),
                *(str(turn.response_items_json or "") for turn in turns),
                *(str(turn.error_message or "") for turn in turns),
                *(str(item.input_json or "") for item in tools),
                *(str(item.error_message or "") for item in tools),
                *(str(item.model_visible_summary or "") for item in observations),
                *(str(item.model_output_json or "") for item in observations),
                *(str(item.facts_json or "") for item in observations),
                *(str(item.error_message or "") for item in observations),
                *(str(item.payload_json or "") for item in artifacts),
                *(str(item.provenance_json or "") for item in artifacts),
                *(str(item.item_json or "") for item in run_items),
                *(str(item.payload_json or "") for item in events),
                *(str(item.steps_json or "") for item in plans),
            ]
            plan = plans[-1] if plans else None
            plan_events = [
                event
                for event in events
                if plan is not None and str(event.run_id or "") == str(plan.run_id)
            ]
            run_traces: list[RunTrace] = []
            for run in runs:
                if run is None:
                    continue
                run_id = str(run.id)
                run_tools = [item for item in tools if str(item.run_id) == run_id]
                run_turns = [item for item in turns if str(item.run_id) == run_id]
                run_fingerprints: list[str] = []
                for artifact in result_artifacts:
                    if str(artifact.run_id) != run_id:
                        continue
                    payload = load_object(str(artifact.payload_json))
                    fingerprint = str(payload.get("queryFingerprint") or "").strip()
                    if fingerprint:
                        run_fingerprints.append(fingerprint)
                run_traces.append(
                    RunTrace(
                        status=str(run.status),
                        error_code=(str(run.error_code) if run.error_code else None),
                        tools=tuple(
                            ToolTrace(
                                name=str(item.tool_name),
                                status=str(item.status),
                                error_code=(
                                    str(item.error_code) if item.error_code else None
                                ),
                                attempt_count=int(item.attempt_count or 0),
                                input_hash=str(item.input_hash or ""),
                                latency_ms=_duration_ms(
                                    item.started_at,
                                    item.completed_at,
                                ),
                            )
                            for item in run_tools
                        ),
                        turn_count=len(run_turns),
                        token_count=int(run.consumed_tokens or 0),
                        latency_ms=_duration_ms(run.started_at, run.completed_at),
                        query_fingerprints=tuple(run_fingerprints),
                    )
                )
            trace = TrialTrace(
                terminal_status=str(final_run.status) if final_run else "runner_failed",
                answer=text,
                tools=tuple(
                    ToolTrace(
                        name=str(item.tool_name),
                        status=str(item.status),
                        error_code=str(item.error_code) if item.error_code else None,
                        attempt_count=int(item.attempt_count or 0),
                        input_hash=str(item.input_hash or ""),
                        latency_ms=_duration_ms(item.started_at, item.completed_at),
                    )
                    for item in tools
                ),
                artifact_types=tuple(str(item.type) for item in artifacts),
                artifact_ids=tuple(str(item.id) for item in artifacts),
                turn_count=len(turns),
                token_count=sum(int(run.consumed_tokens or 0) for run in runs if run),
                input_tokens=sum(
                    int(run.consumed_input_tokens or 0) for run in runs if run
                ),
                output_tokens=sum(
                    int(run.consumed_output_tokens or 0) for run in runs if run
                ),
                # This runner intentionally has no model-price resolver. Persisted
                # zero is an accounting placeholder, not evidence that usage is free.
                cost_usd=None,
                turn_latency_ms=sum(
                    _duration_ms(turn.created_at, turn.completed_at) for turn in turns
                ),
                tool_latency_ms=sum(
                    _duration_ms(item.started_at, item.completed_at) for item in tools
                ),
                provider_retries=sum(
                    int(run.provider_retry_count or 0) for run in runs if run
                ),
                repair_attempts=sum(
                    int(run.repair_attempt_count or 0) for run in runs if run
                ),
                run_id_hashes=tuple(
                    hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
                    for run_id in run_ids
                ),
                run_statuses=tuple(str(run.status) for run in runs if run),
                run_traces=tuple(run_traces),
                turn_efficiency=tuple(turn_efficiency),
                prompt_versions=tuple(str(turn.prompt_version) for turn in turns),
                tool_materialization_hashes=tuple(
                    str(turn.tool_materialization_hash) for turn in turns
                ),
                tool_schema_counts=tuple(
                    _non_negative_int(budget.get("tool_schema_count"))
                    for budget in prompt_budgets
                ),
                tool_schema_tokens=tuple(
                    _non_negative_int(budget.get("tool_schema_tokens"))
                    for budget in prompt_budgets
                ),
                query_fingerprints=tuple(query_fingerprints),
                infrastructure_error=_infrastructure_reason(
                    str(final_run.status) if final_run else "runner_failed",
                    error_code,
                ),
                secret_scan_clean=(not secret or secret not in text),
                durable_secret_scan_clean=(
                    not secret or all(secret not in value for value in durable_surfaces)
                ),
                plan=_plan_trace(plan, plan_events, load_object),
            )
            return trace, (
                json.dumps(
                    {"sql": generated_sql, "parameters": generated_parameters},
                    ensure_ascii=False,
                )
                if generated_sql
                else None
            )

    loop = RunLoop(
        session_factory=session_factory,
        model_factory=lambda _settings: OpenAIModelAdapter.from_config(config),
        registry=build_product_tool_registry(snapshot),
        context_contributors=default_context_contributors(snapshot),
        capability_guidance=default_capability_guidance(snapshot),
        completion=CompletionGate(build_default_completion_policy(snapshot)),
        live_stream=LiveStreamHub(),
    )
    records: list[TrialRecord] = []
    try:
        for repetition in range(1, repetitions + 1):
            ordered = cases if repetition % 2 else tuple(reversed(cases))
            for case in ordered:
                started = time.perf_counter()
                run_ids: list[str] = []
                answer_id = ""
                exception_type: str | None = None
                before = _snapshot_checks(
                    datasource_path, case.safety.database_unchanged_sql
                )
                generated_payload: str | None = None
                try:
                    session_id = create_session(case, repetition)
                    for prompt_index in range(len(case.prompts)):
                        run_id, answer_id = execute_prompt(
                            session_id=session_id,
                            case=case,
                            repetition=repetition,
                            prompt_index=prompt_index,
                        )
                        run_ids.append(run_id)
                    trace, generated_payload = collect(
                        run_ids, answer_id, case
                    )
                except Exception as exc:  # evidence captures the class, never secrets
                    exception_type = type(exc).__name__
                    trace = TrialTrace(
                        terminal_status="runner_failed",
                        infrastructure_error=exception_type,
                    )

                after = _snapshot_checks(
                    datasource_path, case.safety.database_unchanged_sql
                )
                updates: dict[str, Any] = {
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "unchanged_checks": {
                        statement: before.get(statement) == after.get(statement)
                        for statement in case.safety.database_unchanged_sql
                    },
                }
                forbidden = case.safety.forbidden_output_terms
                updates["secret_scan_clean"] = trace.secret_scan_clean and not any(
                    term in trace.answer for term in forbidden
                )
                if case.result is not None and generated_payload:
                    generated = json.loads(generated_payload)
                    updates["generated_result"] = _query_table(
                        datasource_path,
                        generated["sql"],
                        generated.get("parameters"),
                    )
                    updates["golden_result"] = _query_table(
                        datasource_path,
                        case.result.golden_sql,
                    )
                trace = trace.model_copy(update=updates)
                score = score_trial(case, trace)
                records.append(
                    TrialRecord(
                        case_id=case.case_id,
                        category=case.category,
                        capability=case.capability,
                        repetition=repetition,
                        trace=trace,
                        score=score,
                    )
                )
                print(
                    f"[{len(records)}/{len(cases) * repetitions}] {case.case_id} "
                    f"r{repetition}: {score.verdict.value}"
                    + (f" ({exception_type})" if exception_type else ""),
                    flush=True,
                )
    finally:
        loop.close()
        runtime_metadata_engine.dispose()
    return tuple(records), identity
