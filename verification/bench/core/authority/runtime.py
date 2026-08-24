"""Core AuthorityBench runner over production frozen refs and ToolDispatcher."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from engine.agent.completion import CompletionGate, CompletionPolicy
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentMessage, AgentRun, AgentSession, AgentToolInvocation
from engine.resource import ResourceScopeRef
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver
from verification.bench.core.authority.schema import AuthorityCase, load_cases
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.runtime_fixture import isolated_kernel_snapshot
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events
from verification.testkit.synthetic_resources import (
    SYNTHETIC_RESOURCE_KIND,
    ResourceProbeTool,
)


HERE = Path(__file__).resolve().parent


def _run_case(
    session_factory: sessionmaker[Session],
    *,
    suite_id: str,
    case: AuthorityCase,
    repetition: int,
) -> TrialOutcome:
    session_id = f"authority-bench-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    refs = tuple(
        ResourceScopeRef(kind=SYNTHETIC_RESOURCE_KIND, id=resource_id, version=1)
        for resource_id in case.authorized_ids
    )
    with session_factory() as db:
        db.add(AgentSession(id=session_id, project_id=None, title=case.case_id))
        db.commit()
        sessions = SessionRepository(db)
        admission = sessions.admit(
            session_id=session_id,
            resource_refs=refs,
            content=f"Read verification resource {case.requested_id}.",
            idempotency_key=f"{suite_id}:{case.case_id}:{repetition}",
            llm_credential_id="authority-bench-scripted-provider",
            api_base=None,
            model_name="scripted",
            request_payload={"benchmark_suite": suite_id, "case_id": case.case_id},
        )
        lease = sessions.claim(session_id=session_id, owner="authority-bench", ttl_seconds=120)
        if lease is None:
            raise RuntimeError("AuthorityBench could not claim the production Session lease")
        sessions.promote_next_input(lease=lease)
        db.commit()

    scripts = [
        tool_call_events(
            call_id=f"probe-{case.requested_id}",
            tool_name="verification_resource_probe",
            arguments={"resource_id": case.requested_id},
        ),
        answer_events("access granted" if case.expect_access else "access denied"),
    ]

    def model_factory(_settings):
        return ScriptedProvider(scripts.pop(0))

    access_log: list[str] = []
    resolver = CompositeResourceResolver().register(
        SYNTHETIC_RESOURCE_KIND,
        lambda ref: {"id": ref.id, "value": f"value:{ref.id}"},
    ).freeze()
    loop = RunLoop(
        session_factory=session_factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ResourceProbeTool(access_log)),
        context_contributors=(),
        completion=CompletionGate(CompletionPolicy(constraints=(), supports=())),
        definition=AgentDefinition(allowed_tool_groups=("verification",)),
        live_stream=LiveStreamHub(),
        resource_resolver=resolver,
    )
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()

    with session_factory() as db:
        run = db.get(AgentRun, admission.run_id)
        answer = db.get(AgentMessage, admission.assistant_message_id)
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        invocation = invocations[0] if invocations else None
        accessed_authorized = all(item in case.authorized_ids for item in access_log)
        if case.expect_access:
            selection_ok = (
                invocation is not None
                and str(invocation.status) == "succeeded"
                and access_log == [case.requested_id]
            )
        else:
            selection_ok = (
                invocation is not None
                and str(invocation.status) != "succeeded"
                and not access_log
            )
        violations = sum(item not in case.authorized_ids for item in access_log)
        text = str(answer.content or "") if answer is not None else ""
        checks = {
            "completed": run is not None and str(run.status) == "completed",
            "expected_answer": ("granted" in text) == case.expect_access,
            "selection": selection_ok,
            "no_authority_violation": accessed_authorized and violations == 0,
            "single_tool_call": len(invocations) == 1,
        }
        failed = tuple(name for name, passed in checks.items() if not passed)
        return TrialOutcome(
            suite_id=suite_id,
            case_id=case.case_id,
            repetition=repetition,
            verdict="pass" if not failed else "fail",
            metrics={
                "task.success_rate": 1.0 if not failed else 0.0,
                "authority.selection_accuracy": 1.0 if selection_ok else 0.0,
                "authority.violation_count": float(violations),
                "runtime.tool_calls": float(len(invocations)),
            },
            failed_checks=failed,
            evidence={
                "run_status": str(run.status) if run is not None else "missing",
                "invocation_status": str(invocation.status) if invocation is not None else "missing",
                "authorized_ids": case.authorized_ids,
                "access_log": tuple(access_log),
            },
        )


def run_core_authority_bench(
    *,
    output_dir: Path,
    repetitions: int = 1,
    case_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    dataset = load_cases(HERE / manifest.dataset)
    cases = tuple(case for case in dataset.cases if not case_ids or case.case_id in case_ids)
    if not cases:
        raise ValueError("No AuthorityBench cases matched the requested case ids")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    engine = create_migrated_metadata_engine(work_dir / "metadata.sqlite")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with isolated_kernel_snapshot(work_dir / "kernel-dlcs"):
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
        return write_suite_report(output_dir, manifest=manifest, outcomes=outcomes)
    finally:
        engine.dispose()
        resolved_work = work_dir.resolve()
        resolved_parent = output_dir.parent.resolve()
        if resolved_work.parent == resolved_parent and resolved_work.name.startswith("."):
            shutil.rmtree(resolved_work)
