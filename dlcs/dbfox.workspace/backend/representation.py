"""Read bounded file content from its exact, still-available Artifact source."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from dbfox_dlc_api import (
    ArtifactRepresentationDescriptor, ArtifactRepresentationError,
    ArtifactRepresentationOperation, ArtifactRepresentationResult, ArtifactRepresentationStream,
)

from .contracts import FileReadInput, FileReadOutput, WorkspaceCodePatchPayload, WorkspaceFileSnapshotPayload
from .service import WorkspaceError, WorkspaceFile
from .store import WORKSPACE_RESOURCE_KIND, WorkspaceBindingStore

FILE_REPRESENTATION = "dbfox.workspace.file.v1"
FILE_MEDIA_TYPE = "text/plain; charset=utf-8"


def file_read_output(snapshot: WorkspaceFile, input: FileReadInput) -> FileReadOutput:
    """Canonical character page for Tools, user operations and representations."""
    if input.offset > len(snapshot.content):
        raise WorkspaceError("Read offset exceeds the file's character length. Read from offset=0 and reuse next_offset for subsequent pages.")
    content = snapshot.content[input.offset : input.offset + input.limit]
    next_offset = input.offset + len(content)
    return FileReadOutput(
        path=snapshot.relative_path, content=content,
        content_truncated=snapshot.truncated or next_offset < len(snapshot.content),
        size_bytes=snapshot.size_bytes, sha256=snapshot.sha256,
        offset=input.offset, next_offset=next_offset,
    )


class WorkspaceFileRepresentation:
    def __init__(self, store: WorkspaceBindingStore) -> None:
        self._store = store

    def describe(self, artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type not in {"dbfox.workspace.file_snapshot", "dbfox.workspace.code_patch"}:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "此成果不是工作区文件。", status_code=409)
        return ArtifactRepresentationDescriptor(
            representation_type=FILE_REPRESENTATION, version=1,
            operations=(
                ArtifactRepresentationOperation(name="read"),
                ArtifactRepresentationOperation(
                    name="download", result_kind="stream", media_type=FILE_MEDIA_TYPE, purpose="file",
                ),
            ),
        )

    def execute(self, artifact, request, context) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        self.describe(artifact)
        if request.operation == "download":
            if request.parameters:
                raise ArtifactRepresentationError("INVALID_REQUEST", "下载文件不接受参数。")
        elif request.operation != "read" or set(request.parameters) - {"offset", "limit"}:
            raise ArtifactRepresentationError("INVALID_REQUEST", "文件预览仅接受 offset 和 limit。")
        try:
            if artifact.type == "dbfox.workspace.file_snapshot":
                snapshot = WorkspaceFileSnapshotPayload.model_validate(artifact.payload)
                digest = snapshot.sha256
                workspace_id, workspace_version, path = snapshot.workspace_id, snapshot.workspace_version, snapshot.relative_path
            else:
                patch = WorkspaceCodePatchPayload.model_validate(artifact.payload)
                digest = patch.new_sha256
                workspace_id, workspace_version, path = patch.workspace_id, patch.workspace_version, patch.relative_path
            read = FileReadInput.model_validate({"path": path, **request.parameters})
        except ValueError:
            raise ArtifactRepresentationError("INVALID_REQUEST", "文件预览请求或成果记录无效。") from None
        ref = next((ref for ref in artifact.resource_refs
                    if ref.kind == WORKSPACE_RESOURCE_KIND and ref.id == workspace_id and ref.version == workspace_version), None)
        if ref is None:
            raise ArtifactRepresentationError("FORBIDDEN", "此成果没有匹配的文件来源授权。", status_code=403)
        try:
            source = self._store.resolve(ref).read_text_file(read.path)
        except (WorkspaceError, ValueError, KeyError):
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", "原工作区或文件已不可用。", status_code=409) from None
        if source.sha256 != digest:
            raise ArtifactRepresentationError("SOURCE_CHANGED", "文件已修改，无法展示当时的版本；请从项目文件中打开最新内容。", status_code=409)
        if request.operation == "download":
            # The UTF-8 decoder in WorkspaceService preserves the exact bytes.
            return ArtifactRepresentationStream(
                chunks=iter((source.content.encode("utf-8"),)),
                media_type=FILE_MEDIA_TYPE,
                file_name=PurePosixPath(source.relative_path).name,
                metadata={"consistency": "live_reexecution", "source-fingerprint": digest},
            )
        try:
            output = file_read_output(source, read)
        except WorkspaceError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", str(exc), status_code=409) from None
        return ArtifactRepresentationResult(
            representation_type=FILE_REPRESENTATION, representation_version=1, operation="read",
            payload=output.model_dump(mode="json"), consistency="live_reexecution",
            read_at=datetime.now(timezone.utc).isoformat(), read_id=f"file_read_{uuid4().hex}",
            source_version=digest, source_fingerprint=digest,
            notices=("内容来自工作区文件，已核对成果记录中的文件摘要。",),
        )
