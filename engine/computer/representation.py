"""Immutable capture and action evidence, through the existing Representation API."""
from datetime import UTC, datetime
from uuid import uuid4

from engine.agent.artifact import Artifact
from engine.computer.contracts import ACTION_ARTIFACT, ActionEvidence, ComputerError, Observation, REPRESENTATION
from engine.computer.runtime import ComputerRuntime
from engine.representation import (
    ArtifactRepresentationContext, ArtifactRepresentationDescriptor, ArtifactRepresentationError,
    ArtifactRepresentationOperation, ArtifactRepresentationRequest, ArtifactRepresentationResult, ArtifactRepresentationStream,
)


class ComputerRepresentation:
    def __init__(self, runtime: ComputerRuntime) -> None:
        self.runtime = runtime

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        operations = [ArtifactRepresentationOperation(name="read", purpose="model_read")]
        if artifact.type != ACTION_ARTIFACT:
            operations.extend((
                ArtifactRepresentationOperation(name="image", result_kind="stream", media_type="image/png", purpose="model_media"),
                ArtifactRepresentationOperation(name="download", result_kind="stream", media_type="image/png", purpose="file"),
            ))
        return ArtifactRepresentationDescriptor(representation_type=REPRESENTATION, version=1, operations=tuple(operations))

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest,
                context: ArtifactRepresentationContext) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        if request.parameters:
            raise ArtifactRepresentationError("INVALID_REQUEST", "此证据读取不接受额外参数。")
        if artifact.type == ACTION_ARTIFACT:
            payload = ActionEvidence.model_validate(artifact.payload).model_dump(mode="json")
        else:
            observation = Observation.model_validate(artifact.payload)
            payload = observation.model_dump(mode="json")
            if request.operation != "read":
                try:
                    data = self.runtime.read_capture(observation)
                except ComputerError as exc:
                    raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", str(exc), status_code=410 if exc.status == 410 else 409) from None
                return ArtifactRepresentationStream(chunks=iter((data,)), media_type="image/png",
                    file_name=observation.id + ".png", metadata={"sha256": observation.image_sha256})
        return ArtifactRepresentationResult(representation_type=REPRESENTATION, representation_version=1,
            operation=request.operation, payload=payload, consistency="durable_snapshot",
            read_at=datetime.now(UTC).isoformat(), read_id="capture_read_" + uuid4().hex,
            source_version=artifact.id, source_fingerprint=str(payload.get("image_sha256") or artifact.id),
            notices=("截图最多保留 24 小时，并受 256 MB / 512 张本机预算限制。操作记录不代表任务已完成。",))
