"""Read explicitly exposed representations of work products in the current Run."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field, ValidationError

from engine.agent.artifact import Artifact, ArtifactVisibility
from engine.errors import ToolInputError
from engine.json_codec import byte_size, loads
from engine.representation import (
    REPRESENTATION_OPERATION_PATTERN,
    REPRESENTATION_TYPE_PATTERN,
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationError,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
)
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolRunContext,
    ToolSemanticSpec,
)
from engine.tools.runtime.base import ToolInputModel, ToolOutputModel
from engine.tools.runtime.observation import MODEL_RESULT_WINDOW_BYTES


class ArtifactReadSelection(ToolInputModel):
    representation_type: str = Field(pattern=REPRESENTATION_TYPE_PATTERN)
    representation_version: int = Field(ge=1)
    operation: str = Field(pattern=REPRESENTATION_OPERATION_PATTERN)
    parameters_json: str = Field(
        default="{}",
        max_length=8_192,
        description="JSON object for the representation operation; {} uses its defaults.",
    )


class ArtifactReadInput(ToolInputModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    read: ArtifactReadSelection | None = Field(
        default=None, description="Omit to discover how the Artifact can be read or delivered."
    )


class ArtifactReadOutput(ToolOutputModel):
    referenced_artifact_ids: tuple[str, ...]
    artifact_type: str
    artifact_version: int
    representations: tuple[ArtifactRepresentationDescriptor, ...] = ()
    representation: ArtifactRepresentationResult | None = None


class ArtifactReadTool(BaseTool[ArtifactReadInput, ArtifactReadOutput]):
    name = "artifact_read"
    group = "conversation"
    description = (
        "Discover the readable representations and files of an authorized Artifact in the "
        "current conversation. Read a bounded, immutable JSON representation with purpose "
        "model_read by passing its type, version and operation. Files remain Artifact references. "
        "Use the owning capability's tools for live queries or edits."
    )
    input_model = ArtifactReadInput
    output_model = ArtifactReadOutput
    execution = ToolExecutionSpec(
        max_output_bytes=MODEL_RESULT_WINDOW_BYTES,
        capabilities=("metadata_read", "filesystem_read"),
    )
    policy = ToolPolicy(risk_level="safe")
    semantics = ToolSemanticSpec(publishes_artifact_references=True)
    presentation = ToolPresentation(title="查看工件", category="explore")

    def __init__(
        self,
        describe: Callable[[Artifact], tuple[ArtifactRepresentationDescriptor, ...]],
    ) -> None:
        self._describe = describe

    def run(self, tool_input: ArtifactReadInput, context: ToolRunContext) -> ArtifactReadOutput:
        try:
            artifact = context.artifact(tool_input.artifact_id)
        except RuntimeError as error:
            raise ToolInputError("The Artifact is unavailable in this Run.") from error
        if artifact.visibility is ArtifactVisibility.INTERNAL:
            raise ToolInputError("The Artifact is unavailable in this Run.")

        descriptors = self._describe(artifact)
        result = None
        exposed = []
        if tool_input.read is None:
            for descriptor in descriptors:
                operations = tuple(operation for operation in descriptor.operations if operation.purpose)
                if operations:
                    exposed.append(descriptor.model_copy(update={"operations": operations}))
        else:
            result = self._read(context, artifact, descriptors, tool_input.read)

        output = ArtifactReadOutput(
            referenced_artifact_ids=(artifact.id,),
            artifact_type=artifact.type,
            artifact_version=artifact.version,
            representations=tuple(exposed),
            representation=result,
        )
        if byte_size(output) > self.execution.max_output_bytes:
            raise ToolInputError("The Artifact response exceeds the model budget. Request a smaller page or window.")
        return output

    @staticmethod
    def _read(
        context: ToolRunContext,
        artifact: Artifact,
        descriptors: tuple[ArtifactRepresentationDescriptor, ...],
        selection: ArtifactReadSelection,
    ) -> ArtifactRepresentationResult:
        descriptor = next((item for item in descriptors if item.representation_type == selection.representation_type), None)
        if descriptor is None or descriptor.version != selection.representation_version:
            raise ToolInputError("This representation version is unavailable. Inspect the Artifact again.")
        operation = descriptor.operation(selection.operation)
        if operation is None or operation.purpose != "model_read":
            raise ToolInputError("This operation is not exposed for model reads. Use the owning capability or open the Artifact.")
        try:
            parameters = loads(selection.parameters_json)
            if not isinstance(parameters, dict):
                raise ValueError("Parameters must be a JSON object")
            request = ArtifactRepresentationRequest(
                operation=selection.operation, parameters=parameters,
            )
        except (ValidationError, ValueError, RecursionError) as error:
            raise ToolInputError("Representation parameters must be a valid JSON object.") from error
        try:
            result = context.read_artifact_representation(artifact.id, selection.representation_type, request)
        except ArtifactRepresentationError as error:
            raise ToolInputError(f"Artifact representation read failed ({error.code}).") from error
        if result.representation_version != selection.representation_version or result.consistency != "durable_snapshot":
            raise ToolInputError("The Artifact no longer offers the requested immutable representation.")
        return result

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法读取工件。")
        facts = {"artifact_type": output["artifact_type"], "artifact_version": output["artifact_version"]}
        result = output.get("representation")
        if result:
            facts.update(
                representation_type=result["representation_type"],
                operation=result["operation"],
                source_fingerprint=result["source_fingerprint"],
            )
        return ToolObservationProjection(summary="已读取工件。", facts=facts, provider_payload=output)
