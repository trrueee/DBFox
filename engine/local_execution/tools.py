"""Tool Runtime entry points for the trusted Host broker."""

from __future__ import annotations

import platform
import time
from pathlib import PurePosixPath
from typing import Any, cast

from pydantic import Field

from engine.agent.artifact import ArtifactDraft, ArtifactRelationDraft, ArtifactRelationType
from engine.diagnostics.logs import redact_sensitive_text
from engine.errors import ToolInputError
from engine.local_execution.broker import LocalExecutionBroker
from engine.local_execution.command import ExecutionError, find_program, local_environment, prepare
from engine.local_execution.contracts import (
    ACTIVE_STATES, Contract, ExecutionScope, InspectInput, JobInput, JobPage, JobView,
    StartInput, StdinInput, WORKSPACE_KIND, WorkspaceDirectory,
)
from engine.local_execution.representation import RESULT_ARTIFACT
from engine.policy.authority import ExecutionAuthority
from engine.tools.runtime import (
    BaseTool, ToolAdmissionContext, ToolAdmissionDecision, ToolExecutionSpec, ToolObservationProjection,
    ToolOutcome, ToolPolicy, ToolPresentation, ToolResourceRequirement, ToolRunContext, ToolSemanticSpec,
)

_REQUIREMENTS = (ToolResourceRequirement(kind=WORKSPACE_KIND),)
_APPROVAL = ToolPolicy(risk_level="danger", requires_admission=True, requires_approval=True)
_READ = ToolExecutionSpec(
    required_resources=_REQUIREMENTS, concurrency="parallel_safe", capabilities=("metadata_read",), max_output_bytes=160_000,
)
_CHANGE = ToolExecutionSpec(required_resources=_REQUIREMENTS, timeout_seconds=15)
_SPAWN = ToolExecutionSpec(required_resources=_REQUIREMENTS, capabilities=("subprocess",), timeout_seconds=20)
_RISK = "程序将在本机以当前系统用户权限运行，工作目录仅用于选择项目。请核对可执行文件、参数和运行时长。"


def _scope(context: ToolRunContext | ToolAdmissionContext) -> ExecutionScope:
    refs = context.scopes(WORKSPACE_KIND)
    if len(refs) != 1:
        raise ToolInputError("Select exactly one authorized Workspace folder for this command.")
    session_id = context.thread_id if isinstance(context, ToolRunContext) else context.session_id
    return ExecutionScope(session_id, refs[0])


def _status(job: dict) -> dict:
    return {
        "execution_job_id": job["id"],
        **{key: job[key] for key in (
            "state", "reason", "root_exit_code", "active_processes", "output_finalized",
            "first_cursor", "last_cursor", "stdin_open",
        )},
    }


def _review(job: JobView) -> dict:
    return {"job_id": job.id, "executable": job.executable, "cwd": job.cwd}


def _approval_error(exc: Exception) -> ToolAdmissionDecision:
    return ToolAdmissionDecision(
        status="blocked", risk_level="danger",
        reason=str(exc) if isinstance(exc, (ExecutionError, ToolInputError)) else "The authorized Workspace or Job is unavailable.",
    )


class _BrokerTool:
    group = "workspace"

    def __init__(self, broker: LocalExecutionBroker) -> None:
        self.broker = broker

    @staticmethod
    def _authorize(context: ToolRunContext, scope: ExecutionScope, subject: dict) -> ExecutionAuthority:
        authority = context.execution_authority
        if not isinstance(authority, ExecutionAuthority) or authority.invocation_id != context.invocation_id or not (
            context.approval_authorizes(subject, scope.workspace)
        ):
            raise ExecutionError("This operation requires its own valid approval.")
        return authority


class CommandStart(_BrokerTool, BaseTool[StartInput, JobView]):
    name = "command_start"
    description = (
        "Start a real Windows process in the authorized project and return a Job ID. Approval applies once. "
        "Use argv for a direct .exe or shell_script for Windows cmd, pipelines, and .cmd/.bat scripts. "
        "Set non-secret env overrides if needed. Use interactive=true to keep stdin open. Foreground Jobs stop when the Run ends; request background "
        "only if the user wants it to outlive a successful Run. Use command_inspect to wait for real results."
    )
    input_model = StartInput
    output_model = JobView
    policy = _APPROVAL
    execution = _SPAWN
    presentation = ToolPresentation(title="启动本机命令", category="manage")

    def admit(self, input: StartInput, context: ToolAdmissionContext) -> ToolAdmissionDecision:
        try:
            scope = _scope(context)
            resource = self.broker.resolve_workspace(scope.workspace)
            command = prepare(input, resource.command_directory(input.cwd))
        except (KeyError, ValueError, OSError, ToolInputError) as exc:
            return _approval_error(exc)
        return ToolAdmissionDecision(
            status="approval_required", risk_level="danger", reason=_RISK,
            approval_subject=command.subject(), approval_review=command.display(), resource_ref=scope.workspace,
        )

    def run(self, input: StartInput, context: ToolRunContext) -> JobView:
        scope = _scope(context)
        authority = context.execution_authority
        if not isinstance(authority, ExecutionAuthority) or authority.invocation_id != context.invocation_id:
            raise ToolInputError("The command requires approval for this invocation.")
        try:
            return self.broker.start(
                scope=scope, run_id=context.require_request().run_id, invocation_id=context.invocation_id,
                approval_id=authority.approval_id, input=input,
                resource=cast(WorkspaceDirectory, context.resource(scope.workspace)),
                is_approved=lambda command: context.approval_authorizes(command.subject(), scope.workspace),
                is_cancelled=context.is_cancelled,
            )
        except ExecutionError as exc:
            raise ToolInputError(str(exc)) from exc
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The approved Workspace or executable is no longer available.") from exc

    def cancel(self, invocation_id: str) -> None:
        self.broker.cancel_invocation(invocation_id)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="命令启动失败。")
        facts = _status(output)
        return ToolObservationProjection(
            summary="已受理本机命令，请检查 Job 状态与退出码。", facts=facts, provider_payload=facts,
        )


class CommandInspect(_BrokerTool, BaseTool[InspectInput, JobPage]):
    name = "command_inspect"
    description = (
        "Check a Job in this conversation and read up to two retained stdout/stderr chunks. "
        "Use next_cursor as after; tail=true jumps to recent output. "
        "wait_seconds waits for output or a terminal state. A root exit code alone is not completion. "
        "A successful exit has state=exited, root_exit_code=0, active_processes=0, output_finalized=true."
    )
    input_model = InspectInput
    output_model = JobPage
    execution = _READ
    presentation = ToolPresentation(title="查看命令输出", category="explore")

    def run(self, input: InspectInput, context: ToolRunContext) -> JobPage:
        scope = _scope(context)
        deadline = time.monotonic() + input.wait_seconds
        try:
            while True:
                page = self.broker.page(scope, input.job_id, input.after, 2, tail=input.tail)
                if page.job.state not in ACTIVE_STATES or page.next_cursor > input.after or time.monotonic() >= deadline:
                    return page
                if context.is_cancelled():
                    raise ToolInputError("The Job inspection was cancelled.")
                time.sleep(0.15)
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The Job or log cursor is unavailable in this Workspace.") from exc

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法查看命令输出。")
        facts = {**_status(output["job"]), **{key: output[key] for key in ("next_cursor", "cursor_expired", "has_more")}}
        return ToolObservationProjection(
            summary="已读取本机执行状态与输出。", facts=facts, provider_payload={**facts, "chunks": output["chunks"]},
        )


class _JobWrite(Contract):
    job_id: str
    bytes_written: int
    stdin_closed: bool


class CommandStdin(_BrokerTool, BaseTool[StdinInput, _JobWrite]):
    name = "command_stdin"
    description = "Write bounded UTF-8 text to a Job's real stdin pipe, optionally closing it. Requires approval per write. Do not use for credentials."
    input_model = StdinInput
    output_model = _JobWrite
    policy = _APPROVAL
    execution = _CHANGE
    presentation = ToolPresentation(title="写入命令标准输入", category="manage")

    def admit(self, input: StdinInput, context: ToolAdmissionContext) -> ToolAdmissionDecision:
        try:
            scope = _scope(context)
            job = self.broker.get(scope, input.job_id)
            if not job.stdin_open or job.state != "running":
                raise ExecutionError("This Job has no open stdin pipe.")
        except (KeyError, ValueError, OSError, ToolInputError) as exc:
            return _approval_error(exc)
        return ToolAdmissionDecision(
            status="approval_required", risk_level="danger",
            reason="内容将写入正在运行的本机程序。请核对输入，避免在此传递凭据。",
            approval_subject=input.model_dump(mode="json"), approval_review=_review(job), resource_ref=scope.workspace,
        )

    def run(self, input: StdinInput, context: ToolRunContext) -> _JobWrite:
        scope = _scope(context)
        try:
            self._authorize(context, scope, input.model_dump(mode="json"))
            count = self.broker.write(scope, input.job_id, input.text, close=input.close)
        except ExecutionError as exc:
            raise ToolInputError(str(exc)) from exc
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The Job or Workspace is no longer available.") from exc
        return _JobWrite(job_id=input.job_id, bytes_written=count, stdin_closed=input.close)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法写入命令标准输入。")
        return ToolObservationProjection(summary="命令输入已写入。", facts=output, provider_payload=output)


class CommandStop(_BrokerTool, BaseTool[JobInput, JobView]):
    name = "command_stop"
    description = "Request termination of a local Job and its Windows Job Object members. Requires its own approval. Inspect afterward to confirm termination."
    input_model = JobInput
    output_model = JobView
    policy = _APPROVAL
    execution = _CHANGE
    presentation = ToolPresentation(title="停止本机任务", category="manage")

    def admit(self, input: JobInput, context: ToolAdmissionContext) -> ToolAdmissionDecision:
        try:
            scope = _scope(context)
            job = self.broker.get(scope, input.job_id)
            if job.state not in ACTIVE_STATES:
                raise ExecutionError("This Job is already terminal.")
        except (KeyError, ValueError, OSError, ToolInputError) as exc:
            return _approval_error(exc)
        return ToolAdmissionDecision(
            status="approval_required", risk_level="danger", reason="将请求终止本机任务及其进程树。",
            approval_subject=input.model_dump(mode="json"), approval_review=_review(job), resource_ref=scope.workspace,
        )

    def run(self, input: JobInput, context: ToolRunContext) -> JobView:
        scope = _scope(context)
        try:
            self._authorize(context, scope, input.model_dump(mode="json"))
            return self.broker.stop(scope, input.job_id)
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The Job or stop authorization is no longer available.") from exc

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法停止本机任务。")
        facts = _status(output)
        return ToolObservationProjection(summary="已请求停止任务，请检查进程树终态。", facts=facts, provider_payload=facts)


class _ResultInput(JobInput):
    related_artifact_ids: list[str] = Field(default_factory=list, max_length=12)


class CommandResult(_BrokerTool, BaseTool[_ResultInput, JobView]):
    name = "command_result"
    description = (
        "Publish a terminal Job as execution evidence. Optionally link authorized Workspace file snapshots "
        "or code patches by Artifact ID, including generated reports. Then use workbench_open_artifact "
        "to open the evidence. Only the observed exit code and retained logs establish the result."
    )
    input_model = _ResultInput
    output_model = JobView
    execution = _READ
    semantics = ToolSemanticSpec(produces=(RESULT_ARTIFACT,))
    presentation = ToolPresentation(title="交付命令结果", category="manage")

    def run(self, input: _ResultInput, context: ToolRunContext) -> ToolOutcome[JobView]:
        scope = _scope(context)
        try:
            job = self.broker.get(scope, input.job_id)
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The Job is not available in this Workspace.") from exc
        if job.state in ACTIVE_STATES:
            raise ToolInputError("The Job is still active. Inspect it before publishing evidence.")
        relations = []
        for artifact_id in dict.fromkeys(input.related_artifact_ids):
            artifact = context.artifact(artifact_id)
            if scope.workspace not in artifact.resource_refs or artifact.type not in {
                "dbfox.workspace.file_snapshot", "dbfox.workspace.code_patch",
            }:
                raise ToolInputError("Evidence links must refer to file Artifacts in this Workspace binding.")
            relations.append(ArtifactRelationDraft(relation=ArtifactRelationType.SUPPORTS, artifact_id=artifact.id))
        return ToolOutcome(output=job, artifacts=(ArtifactDraft(
            key="execution_result", type=RESULT_ARTIFACT, title="本机命令执行记录",
            summary=f"状态 {job.state} · 退出码 {job.root_exit_code if job.root_exit_code is not None else '未知'}",
            semantic_key=f"execution:{job.id}", payload={"job_id": job.id},
            resource_refs=(scope.workspace,), relations=tuple(relations),
        ),))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法发布命令执行记录。")
        facts = _status(output)
        return ToolObservationProjection(summary="已发布本机命令执行记录。", facts=facts, provider_payload=facts)


class _EnvironmentInput(Contract):
    cwd: str = Field(
        default="", max_length=1024,
        description="Directory relative to the bound project root. Leave empty or use . for that root.",
    )
    programs: list[str] = Field(
        default_factory=lambda: ["git", "python", "py", "node", "npm", "pnpm", "tsc", "dotnet", "cargo"],
        max_length=20,
    )


class _EnvironmentOutput(Contract):
    os: str
    architecture: str
    cwd: str
    programs: dict[str, str | None]
    markers: list[str]


class CommandEnvironment(_BrokerTool, BaseTool[_EnvironmentInput, _EnvironmentOutput]):
    name = "command_environment"
    description = (
        "Probe local OS, working directory, project markers and available program paths without executing "
        "anything. Paths may be .cmd/.bat scripts requiring shell_script approval. Inspect config with file_read "
        "and run approved version or Git commands for deeper checks."
    )
    input_model = _EnvironmentInput
    output_model = _EnvironmentOutput
    execution = _READ.model_copy(update={"capabilities": ("filesystem_read",)})
    presentation = ToolPresentation(title="检查本机开发环境", category="explore")

    def run(self, input: _EnvironmentInput, context: ToolRunContext) -> _EnvironmentOutput:
        scope = _scope(context)
        resource = cast(WorkspaceDirectory, context.resource(scope.workspace))
        env = local_environment()
        try:
            directory = resource.command_directory(input.cwd)
            programs: dict[str, str | None] = {}
            for name in input.programs:
                if not name or len(name) > 260:
                    raise ToolInputError("Invalid program name for discovery.")
                try:
                    programs[name] = str(find_program(name, directory, env, scripts=True))
                except ExecutionError:
                    programs[name] = None
            markers = [name for name in (
                ".git", ".venv", "package.json", "pyproject.toml", "requirements.txt",
                "tsconfig.json", "Cargo.toml", "go.mod", "Makefile",
            ) if (directory / name).exists()]
        except (KeyError, ValueError, OSError) as exc:
            raise ToolInputError("The authorized command directory is unavailable.") from exc
        return _EnvironmentOutput(
            os=platform.platform(), architecture=platform.machine(), cwd=str(directory), programs=programs, markers=markers,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法检查本机开发环境。")
        # The absolute cwd is useful to users. Agent Workspace inputs have a
        # project-relative path contract, even when argv uses an absolute exe.
        return ToolObservationProjection(
            summary="已检查本机开发环境。",
            provider_payload={key: output[key] for key in ("os", "architecture", "programs", "markers")},
        )


def bind_command_run(broker: LocalExecutionBroker, legacy: BaseTool[Any, Any]) -> BaseTool[Any, Any]:
    """Keep the published Workspace v1 schemas on the managed Windows path."""

    class CommandRun(CommandStart):
        name = "command_run"
        description = (
            "Run one approved Windows executable and wait for the process tree and output to finish. "
            "Use command_start and command_inspect for long-running jobs or explicit cmd shell scripts."
        )
        version = "2"
        input_model = legacy.input_model
        output_model = legacy.output_model
        execution = _SPAWN.model_copy(update={"timeout_seconds": 330, "max_output_bytes": 400_000})
        semantics = legacy.semantics
        presentation = legacy.presentation

        @staticmethod
        def _start_input(input: Any) -> StartInput:
            return StartInput(argv=list(input.argv), cwd=input.cwd, timeout_seconds=input.timeout_seconds)

        def admit(self, input: Any, context: ToolAdmissionContext) -> ToolAdmissionDecision:
            try:
                return super().admit(self._start_input(input), context)
            except ValueError as exc:
                return _approval_error(exc)

        def run(self, input: Any, context: ToolRunContext) -> Any:
            job = super().run(self._start_input(input), context)
            scope = _scope(context)
            job = self.broker.wait(scope, job.id, context.is_cancelled)
            if job.state not in {"exited", "timed_out"}:
                raise ToolInputError(f"The command did not complete normally ({job.reason or job.state}).")
            page = self.broker.page(scope, job.id, 0, 64)
            output = "".join(chunk.text for chunk in page.chunks)
            truncated = page.cursor_expired or page.has_more or len(output.encode("utf-8")) > 65536
            output = redact_sensitive_text(output.encode("utf-8")[:65536].decode("utf-8", errors="replace"))
            return self.output_model(
                argv=input.argv, cwd=PurePosixPath(input.cwd.strip().replace("\\", "/")).as_posix(),
                exit_code=job.root_exit_code if job.state == "exited" else None,
                timed_out=job.state == "timed_out", duration_ms=job.duration_ms, output=output[:65536],
                truncated=truncated, output_limit_exceeded=False,
            )

        def project_observation(self, *, status, output, artifacts):
            if status != "success":
                return ToolObservationProjection(summary="项目命令执行失败。")
            facts = {key: output[key] for key in ("exit_code", "timed_out", "duration_ms", "truncated")}
            content = output["output"][:8000]
            return ToolObservationProjection(
                summary="项目命令已超时。" if output["timed_out"] else f"项目命令已结束，退出码 {output['exit_code']}。",
                facts=facts, provider_payload={**facts, "output": content, "observation_truncated": len(content) < len(output["output"])},
            )

    return CommandRun(broker)
