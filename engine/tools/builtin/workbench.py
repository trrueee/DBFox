"""Host presentation tool with the standard Invocation and Observation lifecycle."""

from __future__ import annotations

from pydantic import Field

from engine.agent.artifact import ArtifactVisibility
from engine.errors import ToolInputError
from engine.models import AgentSession
from engine.tools.runtime import (
    BaseTool, ToolExecutionSpec, ToolObservationProjection, ToolPolicy,
    ToolPresentation, ToolRunContext, ToolSemanticSpec,
)
from engine.tools.runtime.base import ToolInputModel, ToolOutputModel
from engine.workbench_presentations import WorkbenchPresentationBroker, WorkbenchPresentationOutcome


class OpenArtifactInput(ToolInputModel):
    artifact_id: str = Field(min_length=1, max_length=128)


class OpenArtifactOutput(ToolOutputModel):
    outcome: WorkbenchPresentationOutcome
    referenced_artifact_ids: tuple[str, ...]


class OpenArtifactTool(BaseTool[OpenArtifactInput, OpenArtifactOutput]):
    name = "workbench_open_artifact"
    group = "conversation"
    description = (
        "Use only when the user asks to open an existing Artifact in the current Dock. "
        "The Artifact must be available to this Run. 'opened' means the active Workbench "
        "applied the tab selection, while 'unconfirmed' means no UI receipt arrived. "
        "Do not retry an unconfirmed presentation; the user can open the Artifact from the conversation."
    )
    input_model = OpenArtifactInput
    output_model = OpenArtifactOutput
    execution = ToolExecutionSpec(timeout_seconds=7, capabilities=("metadata_read",))
    policy = ToolPolicy(risk_level="safe")
    semantics = ToolSemanticSpec(publishes_artifact_references=True, contributes_progress=False)
    presentation = ToolPresentation(title="在 Dock 打开工件", category="explore")

    def __init__(self, broker: WorkbenchPresentationBroker) -> None:
        self._broker = broker

    def cancel(self, invocation_id: str) -> None:
        self._broker.cancel(invocation_id)

    def run(self, tool_input: OpenArtifactInput, context: ToolRunContext) -> OpenArtifactOutput:
        try:
            artifact = context.artifact(tool_input.artifact_id)
        except RuntimeError as error:
            raise ToolInputError("The Artifact is unavailable in this Run.") from error
        session_id = context.require_request().session_id
        session = context.require_metadata().get(AgentSession, session_id)
        if (artifact.visibility is ArtifactVisibility.INTERNAL or artifact.session_id != session_id
            or session is None or session.deleted_at is not None or not session.project_id):
            raise ToolInputError("The Artifact cannot be opened in this Workbench.")
        outcome = self._broker.present(
            artifact=artifact,
            invocation_id=context.invocation_id,
            project_id=str(session.project_id),
            cancelled=context.is_cancelled,
            deadline=context.deadline,
        )
        return OpenArtifactOutput(outcome=outcome, referenced_artifact_ids=(artifact.id,))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="无法请求打开工件。")
        summary = {
            "opened": "已在当前 Dock 打开工件。",
            "not_opened": "工作台未应用打开请求。",
            "unconfirmed": "工作台未确认打开结果。",
        }[output["outcome"]]
        return ToolObservationProjection(summary=summary, facts=output)
