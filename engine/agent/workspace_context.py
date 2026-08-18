"""Workspace Context contributor for the P7 vertical slice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.context_fragment import ContextContributionInput, ContextFragment
from engine.json_codec import loads
from engine.models import AgentArtifactRecord, AgentObservationRecord
from engine.tools.runtime.resource_context import resolve_workspace_resource
from engine.workspace.read_service import WorkspaceReadError, WorkspaceReadService

WORKSPACE_FILE_SNAPSHOT_CAPABILITY = "dbfox.workspace.file_snapshot"
_MAX_FRAGMENTS = 8
_MAX_REHYDRATED_CONTENT_CHARS = 3_600


def _json_list(value: str | None) -> list[str]:
    try:
        loaded = loads(value or "[]")
    except Exception:
        return []
    return [str(item) for item in loaded if isinstance(item, str)] if isinstance(loaded, list) else []


def _capabilities(value: str | None) -> list[str]:
    try:
        loaded = loads(value or "[]")
    except Exception:
        return []
    return [str(item) for item in loaded if isinstance(item, str)] if isinstance(loaded, list) else []


class WorkspaceContextContributor:
    id = "dbfox.workspace"

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        input: ContextContributionInput,
    ) -> tuple[ContextFragment, ...]:
        workspace_scopes = {
            (
                str(scope.id),
                str(scope.version or ""),
            )
            for scope in input.resource_refs
            if scope.kind == "workspace" and scope.id
        }
        if not workspace_scopes:
            return ()
        workspaces: dict[tuple[str, str], WorkspaceReadService] = {}
        for scope in input.resource_refs:
            if scope.kind != "workspace" or not scope.id:
                continue
            key = (str(scope.id), str(scope.version or ""))
            try:
                workspaces[key] = resolve_workspace_resource(self.session, scope)
            except ValueError:
                continue
        rows = self.session.execute(
            select(AgentObservationRecord)
            .where(
                AgentObservationRecord.session_id == input.session_id,
                AgentObservationRecord.status == "succeeded",
            )
            .order_by(AgentObservationRecord.created_at.desc(), AgentObservationRecord.sequence.desc())
            .limit(_MAX_FRAGMENTS * 4)
        ).scalars()

        fragments: list[ContextFragment] = []
        for observation in rows:
            if WORKSPACE_FILE_SNAPSHOT_CAPABILITY not in _capabilities(
                observation.semantic_capabilities_json
            ):
                continue
            artifact_ids = _json_list(observation.artifact_ids_json)
            if not artifact_ids:
                continue
            artifacts = self.session.execute(
                select(AgentArtifactRecord).where(
                    AgentArtifactRecord.id.in_(artifact_ids),
                    AgentArtifactRecord.type == "dbfox.workspace.file_snapshot",
                )
            ).scalars()
            for artifact in artifacts:
                try:
                    payload = loads(artifact.payload_json)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                relative_path = str(payload.get("relativePath") or "")
                sha256 = str(payload.get("sha256") or "")
                workspace_id = str(payload.get("workspaceId") or "")
                workspace_version = str(payload.get("workspaceVersion") or "")
                if not relative_path:
                    continue
                workspace = workspaces.get((workspace_id, workspace_version))
                if workspace is None:
                    continue
                try:
                    snapshot = workspace.read_text_file(relative_path)
                except WorkspaceReadError:
                    continue
                if snapshot.sha256 != sha256:
                    continue
                content = snapshot.content[:_MAX_REHYDRATED_CONTENT_CHARS]
                fragments.append(
                    ContextFragment(
                        source_id="dbfox.workspace",
                        source_version=str(observation.id),
                        lane="resource",
                        content=(
                            f"workspace file snapshot: {relative_path}\n"
                            f"sha256: {sha256}\n"
                            f"content:\n{content}"
                        ),
                        provenance={
                            "artifact_id": str(artifact.id),
                            "observation_id": str(observation.id),
                            "relative_path": relative_path,
                            "content_truncated": len(snapshot.content)
                            > _MAX_REHYDRATED_CONTENT_CHARS,
                        },
                    )
                )
                if len(fragments) >= _MAX_FRAGMENTS:
                    return tuple(fragments)
        return tuple(fragments)
