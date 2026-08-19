from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.artifact import ArtifactDraft, register_artifact_payload_contract
from engine.errors import ToolInputError
from engine.models import AgentArtifactRecord
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolPolicy,
    ToolPresentation,
    ToolInputModel,
    ToolOutputModel,
)
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.observation import ToolObservationProjection
from engine.tools.runtime.result import ToolOutcome
from engine.tools.runtime.semantics import ToolSemanticSpec
from engine.json_codec import JsonCodecError, loads


_REMOTE_JOB_ARTIFACT_TYPE = "dbfox.remote_job"
_JOB_SEMANTIC_KEY_PREFIX = "remote_job:"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _remote_job_semantic_id(job_id: str) -> str:
    return f"{_JOB_SEMANTIC_KEY_PREFIX}{job_id}"


def _latest_job_row(
    db: Session,
    session_id: str,
    job_id: str,
) -> AgentArtifactRecord:
    statement = (
        select(AgentArtifactRecord)
        .where(
            AgentArtifactRecord.session_id == session_id,
            AgentArtifactRecord.type == _REMOTE_JOB_ARTIFACT_TYPE,
            AgentArtifactRecord.semantic_id == _remote_job_semantic_id(job_id),
        )
        .order_by(
            AgentArtifactRecord.version.desc(),
            AgentArtifactRecord.created_at.desc(),
        )
    )
    row = db.execute(statement).scalars().first()
    if row is None:
        raise ToolInputError("job_id 找不到对应的远端任务。")
    return row


def _artifact_payload(row: AgentArtifactRecord) -> dict:
    try:
        value = loads(str(row.payload_json or "{}"))
        return dict(value) if isinstance(value, dict) else {}
    except JsonCodecError:
        return {}


def _remote_job_status_from_payload(payload: dict) -> str:
    return str(payload.get("status") or "queued").strip()


def _latest_remote_job_payload(
    db: Session,
    session_id: str,
    job_id: str,
) -> dict:
    row = _latest_job_row(db, session_id, job_id)
    from engine.agent.repositories.artifact import validate_artifact_payload

    payload = validate_artifact_payload(
        _REMOTE_JOB_ARTIFACT_TYPE,
        _artifact_payload(row),
        schema_version=int(row.schema_version or 1),
    )
    return payload


def _project_remote_job_observation(
    *,
    tool_name: str,
    status: str,
    output: dict,
) -> ToolObservationProjection:
    if status != "success":
        return ToolObservationProjection(summary=f"{tool_name} 未能完成。")
    return ToolObservationProjection(
        summary=(
            f"Remote job {output.get('job_id', '')} is "
            f"{output.get('status', 'unknown')}."
        ),
        facts={
            key: output[key]
            for key in ("job_id", "status", "command", "run_id", "turn_id", "updated_at")
            if key in output
        },
    )


class RemoteJobSubmitInput(ToolInputModel):
    command: str = Field(min_length=1, max_length=4_000)
    command_type: str = Field(
        default="run",
        max_length=64,
    )


class RemoteJobStatusInput(ToolInputModel):
    job_id: str = Field(min_length=1, max_length=64)


class RemoteJobCancelInput(ToolInputModel):
    job_id: str = Field(min_length=1, max_length=64)


class _RemoteJobOutput(ToolOutputModel):
    job_id: str = Field(min_length=1, max_length=64)
    status: str = Field(pattern=r"^(queued|running|succeeded|failed|cancelled)$")
    command: str
    run_id: str
    turn_id: str | None = None
    updated_at: str


class RemoteJobSubmitOutput(_RemoteJobOutput):
    pass


class RemoteJobStatusOutput(_RemoteJobOutput):
    pass


class RemoteJobCancelOutput(_RemoteJobOutput):
    pass


class _RemoteJobArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1, max_length=64)
    command: str
    command_type: str = Field(min_length=1, max_length=64)
    status: str = Field(pattern=r"^(queued|running|succeeded|failed|cancelled)$")
    run_id: str = Field(min_length=1)
    turn_id: str | None = None
    updated_at: str
    version: int = 1

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_artifact_id(cls, value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "artifact_id"}
        return value


register_artifact_payload_contract(_REMOTE_JOB_ARTIFACT_TYPE, 1, _RemoteJobArtifactPayload)


class RemoteJobSubmitTool(BaseTool[RemoteJobSubmitInput, RemoteJobSubmitOutput]):
    name = "remote_job_submit"
    group = "remote_job"
    description = "提交一个外部异步任务，返回可供跨会话跟踪的 job_id。"
    input_model = RemoteJobSubmitInput
    output_model = RemoteJobSubmitOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="never_retry",
        retryable=False,
        max_retries=0,
        concurrency="sequential",
        max_output_bytes=1_000_000,
        backend="in_process",
        capabilities=(),
        required_resource_kinds=(),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.remote_job",),
        contributes_progress=True,
        publishes_artifact_references=False,
    )
    presentation = ToolPresentation(
        title="提交远端任务",
        category="manage",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: RemoteJobSubmitInput,
        context: ToolRunContext,
    ) -> ToolOutcome[RemoteJobSubmitOutput]:
        request = context.require_request()
        job_id = f"job_{uuid4().hex}"
        now = _utc_now()
        status = "queued"
        payload = {
            "job_id": job_id,
            "command": input.command,
            "command_type": input.command_type,
            "status": status,
            "run_id": str(request.run_id),
            "turn_id": str(request.turn_id),
            "updated_at": now,
            "version": 1,
        }
        output = RemoteJobSubmitOutput(
            job_id=job_id,
            status=status,
            command=input.command,
            run_id=str(request.run_id),
            turn_id=str(request.turn_id),
            updated_at=now,
        )
        artifact = ArtifactDraft(
            key="remote_job",
            type=_REMOTE_JOB_ARTIFACT_TYPE,
            schema_version=1,
            title=f"Remote Job {job_id}",
            payload=payload,
            semantic_key=_remote_job_semantic_id(job_id),
            summary=f"Submit remote job: {input.command_type}",
        )
        return ToolOutcome(output=output, artifacts=(artifact,))

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        return _project_remote_job_observation(
            tool_name=self.name,
            status=status,
            output=output,
        )


class RemoteJobStatusTool(BaseTool[RemoteJobStatusInput, RemoteJobStatusOutput]):
    name = "remote_job_status"
    group = "remote_job"
    description = "读取同 Session 中某个远端任务的最新状态快照。"
    input_model = RemoteJobStatusInput
    output_model = RemoteJobStatusOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="never_retry",
        retryable=False,
        max_retries=0,
        concurrency="sequential",
        max_output_bytes=1_000_000,
        backend="in_process",
        capabilities=("metadata_read",),
        required_resource_kinds=(),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.remote_job",),
        contributes_progress=True,
        publishes_artifact_references=False,
    )
    presentation = ToolPresentation(
        title="查询远端任务状态",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: RemoteJobStatusInput,
        context: ToolRunContext,
    ) -> RemoteJobStatusOutput:
        db = context.require_metadata()
        payload = _latest_remote_job_payload(
            db,
            context.thread_id,
            input.job_id,
        )
        status = _remote_job_status_from_payload(payload)
        return RemoteJobStatusOutput(
            job_id=input.job_id,
            status=status,
            command=str(payload.get("command") or ""),
            run_id=str(payload.get("run_id") or ""),
            turn_id=payload.get("turn_id"),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        return _project_remote_job_observation(
            tool_name=self.name,
            status=status,
            output=output,
        )


class RemoteJobCancelTool(BaseTool[RemoteJobCancelInput, RemoteJobCancelOutput]):
    name = "remote_job_cancel"
    group = "remote_job"
    description = "取消一个尚未完成的远端任务；若任务已终态返回当前状态。"
    input_model = RemoteJobCancelInput
    output_model = RemoteJobCancelOutput
    version = "1"
    policy = ToolPolicy(risk_level="warning")
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="never_retry",
        retryable=False,
        max_retries=0,
        concurrency="sequential",
        max_output_bytes=1_000_000,
        backend="in_process",
        capabilities=("metadata_read",),
        required_resource_kinds=(),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.remote_job",),
        contributes_progress=True,
        publishes_artifact_references=False,
    )
    presentation = ToolPresentation(
        title="取消远端任务",
        category="manage",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: RemoteJobCancelInput,
        context: ToolRunContext,
    ) -> ToolOutcome[RemoteJobCancelOutput]:
        db = context.require_metadata()
        request = context.require_request()
        row = _latest_job_row(db, context.thread_id, input.job_id)
        from engine.agent.repositories.artifact import validate_artifact_payload

        payload = validate_artifact_payload(
            _REMOTE_JOB_ARTIFACT_TYPE,
            _artifact_payload(row),
            schema_version=int(row.schema_version or 1),
        )
        # A legacy v1 payload may still carry the formerly self-generated ID;
        # carry only the canonical job state into the next Artifact version.
        payload.pop("artifact_id", None)
        status = _remote_job_status_from_payload(payload)
        if status in {"succeeded", "failed", "cancelled"}:
            return RemoteJobCancelOutput(
                job_id=input.job_id,
                status=status,
                command=str(payload.get("command") or ""),
                run_id=str(row.run_id),
                turn_id=str(row.turn_id) if row.turn_id else None,
                updated_at=str(payload.get("updated_at") or ""),
            )

        now = _utc_now()
        payload.update(
            {
                "status": "cancelled",
                "run_id": str(request.run_id),
                "turn_id": str(request.turn_id),
                "updated_at": now,
            }
        )
        cancel_draft = ArtifactDraft(
            key="remote_job",
            type=_REMOTE_JOB_ARTIFACT_TYPE,
            schema_version=1,
            title=f"Remote Job {input.job_id} cancelled",
            payload=payload,
            semantic_key=_remote_job_semantic_id(input.job_id),
            summary="Remote job was cancelled by operator.",
        )
        return ToolOutcome(
            output=RemoteJobCancelOutput(
                job_id=input.job_id,
                status="cancelled",
                command=str(payload.get("command") or ""),
                run_id=str(request.run_id),
                turn_id=str(request.turn_id),
                updated_at=now,
            ),
            artifacts=(cancel_draft,),
        )

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        return _project_remote_job_observation(
            tool_name=self.name,
            status=status,
            output=output,
        )
