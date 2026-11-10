"""Execution evidence is issued by Tool settlement and resolves to retained Job output."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.artifact import Artifact
from engine.local_execution.broker import LocalExecutionBroker
from engine.local_execution.contracts import ExecutionScope, JobInput, WORKSPACE_KIND
from engine.representation import (
    ArtifactRepresentationContext, ArtifactRepresentationDescriptor, ArtifactRepresentationError,
    ArtifactRepresentationOperation, ArtifactRepresentationRequest, ArtifactRepresentationResult,
)

RESULT_ARTIFACT = "dbfox.workspace.command_result"
LOG_REPRESENTATION = "dbfox.workspace.execution_log.v1"


class ExecutionResultPayload(JobInput):
    pass


class LogReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after: int = Field(default=0, ge=0, le=2**53 - 1)
    tail: bool = False
    limit: int = Field(default=2, ge=1, le=16)


class ExecutionLogRepresentation:
    def __init__(self, broker: LocalExecutionBroker) -> None:
        self.broker = broker

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        return ArtifactRepresentationDescriptor(
            representation_type=LOG_REPRESENTATION, version=1,
            operations=(
                ArtifactRepresentationOperation(name="read", purpose="model_read"),
                ArtifactRepresentationOperation(name="page"),
            ),
        )

    def execute(
        self, artifact: Artifact, request: ArtifactRepresentationRequest, context: ArtifactRepresentationContext,
    ) -> ArtifactRepresentationResult:
        try:
            read = LogReadInput.model_validate(request.parameters)
            payload = ExecutionResultPayload.model_validate(artifact.payload)
        except ValueError:
            raise ArtifactRepresentationError("INVALID_REQUEST", "执行日志请求无效。") from None
        scope = next((ref for ref in artifact.resource_refs if ref.kind == WORKSPACE_KIND), None)
        if scope is None:
            raise ArtifactRepresentationError("FORBIDDEN", "此成果缺少项目执行来源。", status_code=403)
        try:
            limit = min(2, read.limit) if request.operation == "read" else read.limit
            page = self.broker.page(
                ExecutionScope(artifact.session_id, scope), payload.job_id, read.after, limit, tail=read.tail,
            )
        except (KeyError, ValueError, OSError):
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", "原执行任务或工作区已不可用。", status_code=409) from None
        return ArtifactRepresentationResult(
            representation_type=LOG_REPRESENTATION, representation_version=1, operation=request.operation,
            payload=page.model_dump(mode="json"), consistency="durable_snapshot",
            read_at=datetime.now(UTC).isoformat(), read_id=f"job_log_{uuid4().hex}",
            source_version=page.job.id, source_fingerprint=f"{page.job.id}:{page.job.first_cursor}:{page.job.last_cursor}",
            notices=("输出按采集顺序显示，日志依照本机保留规则滚动清理。",),
        )
