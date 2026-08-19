"""GitHub Context contributor for rehydrating previously read file snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.context_fragment import ContextContributionInput, ContextFragment
from engine.github.contracts import GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE
from engine.github.resource import resolve_github_repository
from engine.github.service import GithubReadService, GithubServiceError
from engine.json_codec import loads
from engine.models import AgentArtifactRecord, AgentObservationRecord

MAX_GITHUB_CONTEXT_FILES = 4
MAX_CHARS_PER_FILE = 4_000
MAX_TOTAL_CONTEXT_CHARS = 12_000


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


class GitHubContextContributor:
    id = "dbfox.github"

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        input: ContextContributionInput,
    ) -> tuple[ContextFragment, ...]:
        # Filter for github.repository scopes in the current input
        github_scopes = {
            str(scope.id): str(scope.version or "")
            for scope in input.resource_refs
            if scope.kind == "github.repository" and scope.id
        }
        if not github_scopes:
            return ()

        # Resolve services for all authorized github repository scopes
        services: dict[str, GithubReadService] = {}
        for scope in input.resource_refs:
            if scope.kind != "github.repository" or not scope.id:
                continue
            try:
                services[str(scope.id)] = resolve_github_repository(self.session, scope)
            except ValueError:
                continue

        if not services:
            return ()

        # Find succeeded observations in this session
        rows = self.session.execute(
            select(AgentObservationRecord)
            .where(
                AgentObservationRecord.session_id == input.session_id,
                AgentObservationRecord.status == "succeeded",
            )
            .order_by(AgentObservationRecord.created_at.desc(), AgentObservationRecord.sequence.desc())
            .limit(MAX_GITHUB_CONTEXT_FILES * 4)
        ).scalars().all()

        fragments: list[ContextFragment] = []
        total_chars = 0
        seen_files: set[tuple[str, str]] = set()

        for observation in rows:
            if GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE not in _capabilities(
                observation.semantic_capabilities_json
            ):
                continue

            artifact_ids = _json_list(observation.artifact_ids_json)
            if not artifact_ids:
                continue

            artifacts = self.session.execute(
                select(AgentArtifactRecord).where(
                    AgentArtifactRecord.id.in_(artifact_ids),
                    AgentArtifactRecord.type == GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
                )
            ).scalars().all()

            for artifact in artifacts:
                try:
                    payload = loads(artifact.payload_json)
                except Exception:
                    continue

                if not isinstance(payload, dict):
                    continue

                binding_id = str(payload.get("repositoryBindingId") or "")
                revision = str(payload.get("revision") or "")
                relative_path = str(payload.get("relativePath") or "")
                content_sha256 = str(payload.get("contentSha256") or "")

                if not binding_id or not relative_path or not content_sha256:
                    continue

                # Must match current frozen resource ref
                if github_scopes.get(binding_id) != revision:
                    continue

                service = services.get(binding_id)
                if service is None or service.revision != revision:
                    continue

                file_key = (binding_id, relative_path)
                if file_key in seen_files:
                    continue

                try:
                    _path, _rev, _size, sha256, content, _truncated, _blob = service.read_file(relative_path)
                except (GithubServiceError, Exception):
                    continue

                # Verify freshness hash
                if sha256 != content_sha256:
                    continue

                seen_files.add(file_key)
                bounded_content = content[:MAX_CHARS_PER_FILE]

                if total_chars + len(bounded_content) > MAX_TOTAL_CONTEXT_CHARS:
                    remaining_budget = MAX_TOTAL_CONTEXT_CHARS - total_chars
                    if remaining_budget <= 0:
                        return tuple(fragments)
                    bounded_content = bounded_content[:remaining_budget]

                total_chars += len(bounded_content)

                fragments.append(
                    ContextFragment(
                        source_id="dbfox.github",
                        source_version=str(observation.id),
                        lane="resource",
                        content=(
                            f"github file snapshot: {service.owner}/{service.repository} @ {revision[:7]}\n"
                            f"path: {relative_path}\n"
                            f"sha256: {sha256}\n"
                            f"content:\n{bounded_content}"
                        ),
                        provenance={
                            "artifact_id": str(artifact.id),
                            "observation_id": str(observation.id),
                            "binding_id": binding_id,
                            "relative_path": relative_path,
                            "revision": revision,
                            "content_truncated": len(content) > len(bounded_content),
                        },
                    )
                )

                if len(fragments) >= MAX_GITHUB_CONTEXT_FILES or total_chars >= MAX_TOTAL_CONTEXT_CHARS:
                    return tuple(fragments)

        return tuple(fragments)
