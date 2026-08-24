"""Deterministic CoreBench execution through the production Agent RunLoop."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import time
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from engine.agent.completion import CompletionGate, CompletionPolicy
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentMessage, AgentRun, AgentSession, AgentToolInvocation, AgentTurn
from verification.bench.core.loop.schema import CoreLoopCase, ScriptStep, load_cases
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.agent_tools import verification_registry
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import (
    ScriptedProvider,
    answer_events,
    tool_call_events,
)


HERE = Path(__file__).resolve().parent


def _events(step: ScriptStep, *, call_id: str):
    if step.kind == "answer":
        return answer_events(step.content)
    return tool_call_events(
        call_id=call_id,
        tool_name=step.tool_name,
        arguments=step.arguments,
    )


def _run_case(
    session_factory: sessionmaker[Session],
    *,
    suite_id: str,
    case: CoreLoopCase,
    repetition: int,
) -> TrialOutcome:
    session_id = f"core-bench-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    with session_factory() as db:
        db.add(AgentSession(id=session_id, project_id=None, title=case.case_id))
        db.commit()
        sessions = SessionRepository(db)
        admission = sessions.admit(
            session_id=session_id,
            resource_refs=(),
            content=case.prompt,
            idempotency_key=f"{suite_id}:{case.case_id}:{repetition}",
            llm_credential_id="core-bench-scripted-provider",
            api_base=None,
            model_name="scripted",
            request_payload={"benchmark_suite": suite_id, "case_id": case.case_id},
        )
        lease = sessions.claim(
            session_id=session_id,
            owner="core-bench",
            ttl_seconds=120,
        )
        if lease is None:
            raise RuntimeError("CoreBench could not claim the production Session lease")
        sessions.promote_next_input(lease=lease)
        db.commit()

    queued_steps = list(enumerate(case.steps, start=1))

    def model_factory(_settings: Any) -> ScriptedProvider:
        if not queued_steps:
            return ScriptedProvider(answer_events("script exhausted"))
        index, step = queued_steps.pop(0)
        return ScriptedProvider(_events(step, call_id=f"{case.case_id}-{index}"))

    loop = RunLoop(
        session_factory=session_factory,
        model_factory=model_factory,
        registry=verification_registry(),
        context_contributors=(),
        completion=CompletionGate(CompletionPolicy(constraints=(), supports=())),
        definition=AgentDefinition(allowed_tool_groups=("verification",)),
        live_stream=LiveStreamHub(),
    )
    started = time.perf_counter()
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    latency_ms = (time.perf_counter() - started) * 1_000

    with session_factory() as db:
        run = db.get(AgentRun, admission.run_id)
        answer = db.get(AgentMessage, admission.assistant_message_id)
        turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).count()
        invocations = (
            db.query(AgentToolInvocation)
            .filter_by(run_id=admission.run_id)
            .order_by(AgentToolInvocation.created_at, AgentToolInvocation.id)
            .all()
        )
        tool_names = tuple(str(item.tool_name) for item in invocations)
        hashes = Counter(str(item.input_hash) for item in invocations)
        duplicate_calls = sum(max(0, count - 1) for count in hashes.values())
        text = str(answer.content or "") if answer is not None else ""
        checks = {
            "completed": run is not None and str(run.status) == "completed",
            "answer_terms": all(
                term.casefold() in text.casefold() for term in case.required_answer_terms
            ),
            "required_tools": tool_names == case.required_tools,
            "turn_budget": turns <= case.max_turns,
            "tool_budget": len(invocations) <= case.max_tool_calls,
            "all_tools_succeeded": all(
                str(item.status) == "succeeded" for item in invocations
            ),
        }
        failed = tuple(name for name, passed in checks.items() if not passed)
        return TrialOutcome(
            suite_id=suite_id,
            case_id=case.case_id,
            repetition=repetition,
            verdict="pass" if not failed else "fail",
            metrics={
                "task.success_rate": 1.0 if not failed else 0.0,
                "runtime.turns": float(turns),
                "runtime.tool_calls": float(len(invocations)),
                "runtime.duplicate_tool_calls": float(duplicate_calls),
            },
            failed_checks=failed,
            evidence={
                "run_status": str(run.status) if run is not None else "missing",
                "tool_names": tool_names,
                "latency_ms": latency_ms,
            },
        )


def run_core_loop_bench(
    *,
    output_dir: Path,
    repetitions: int = 1,
    case_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    dataset = load_cases(HERE / manifest.dataset)
    cases = tuple(
        case for case in dataset.cases if not case_ids or case.case_id in case_ids
    )
    if not cases:
        raise ValueError("No CoreBench cases matched the requested case ids")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    engine = create_migrated_metadata_engine(work_dir / "metadata.sqlite")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        outcomes = tuple(
            _run_case(
                factory,
                suite_id=manifest.suite_id,
                case=case,
                repetition=repetition,
            )
            for case in cases
            for repetition in range(1, repetitions + 1)
        )
        return write_suite_report(
            output_dir,
            manifest=manifest,
            outcomes=outcomes,
        )
    finally:
        engine.dispose()
        resolved_work = work_dir.resolve()
        resolved_parent = output_dir.parent.resolve()
        if resolved_work.parent == resolved_parent and resolved_work.name.startswith("."):
            shutil.rmtree(resolved_work)
