"""Workspace read-only file tool and FileSnapshot Artifact contract.

This is P7's first real model-visible capability. The tool only receives an
authorized ``workspace`` resource through ToolRunContext; it has no path to a
global filesystem manager or container.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.artifact import (
    ArtifactDraft,
    register_artifact_payload_contract,
)
from engine.errors import ToolInputError
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolPolicy,
    ToolPresentation,
)
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.result import ToolOutcome, ToolReconciliation
from engine.tools.runtime.semantics import ToolSemanticSpec
from engine.workspace.read_service import WorkspaceReadError, WorkspaceReadService
from engine.workspace.patch_service import (
    WorkspacePatchConflict,
    WorkspacePatchError,
    WorkspacePatchService,
)

MAX_FILE_READ_CHARS = 12_000
MAX_WORKSPACE_PATCH_CHARS = 1_048_576


class FileReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(
        min_length=1,
        max_length=1_024,
        description="Workspace-relative UTF-8 text file path, for example src/app.py.",
    )


class FileReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    content: str = Field(max_length=MAX_FILE_READ_CHARS)
    content_truncated: bool
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    readable_chars: int = Field(ge=0)


class FileSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(
        min_length=1,
        max_length=200,
        description="Case-insensitive filename substring.",
    )
    path_prefix: str = Field(
        default="",
        max_length=1_024,
        description="Optional workspace-relative directory prefix.",
    )
    limit: int = Field(default=20, ge=1, le=100)


class FileSearchMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    relative_path: str
    is_dir: bool


class FileSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    path_prefix: str
    matches: list[FileSearchMatch]
    returned_count: int = Field(ge=0)
    truncated: bool


class WorkspaceFileSearchTool(BaseTool[FileSearchInput, FileSearchOutput]):
    name = "file_search"
    group = "workspace"
    description = (
        "List matching file or directory names inside the current Project "
        "workspace. Results are bounded and workspace-root-relative."
    )
    input_model = FileSearchInput
    output_model = FileSearchOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=200_000,
        backend="in_process",
        capabilities=("filesystem_read",),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.workspace.file_search",),
        contributes_progress=True,
    )
    presentation = ToolPresentation(
        title="搜索项目文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(self, input: FileSearchInput, context: ToolRunContext) -> FileSearchOutput:
        workspace = context.require_resource("workspace")
        if not isinstance(workspace, WorkspaceReadService):
            raise RuntimeError("Workspace resource did not resolve to a WorkspaceReadService")
        try:
            entries = workspace.list_directory(input.path_prefix)
        except WorkspaceReadError as exc:
            raise ToolInputError("无法读取该项目文件夹。") from exc
        needle = input.query.casefold()
        matches = [
            FileSearchMatch(
                name=entry.name,
                relative_path=entry.relative_path,
                is_dir=entry.is_dir,
            )
            for entry in entries
            if needle in entry.name.casefold()
        ][: input.limit]
        return FileSearchOutput(
            query=input.query,
            path_prefix=input.path_prefix,
            matches=matches,
            returned_count=len(matches),
            truncated=len(matches) < sum(
                1 for entry in entries if needle in entry.name.casefold()
            ),
        )


class WorkspaceFileReadTool(BaseTool[FileReadInput, FileReadOutput]):
    name = "file_read"
    group = "workspace"
    description = (
        "Read a bounded UTF-8 text file from the current Project workspace. "
        "Only relative paths inside the approved workspace root are allowed; "
        "binary, oversized or non-UTF-8 files are rejected."
    )
    input_model = FileReadInput
    output_model = FileReadOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=1_000_000,
        backend="in_process",
        capabilities=("filesystem_read",),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.workspace.file_snapshot",),
        contributes_progress=True,
        publishes_artifact_references=False,
    )
    presentation = ToolPresentation(
        title="读取项目文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(self, input: FileReadInput, context: ToolRunContext) -> ToolOutcome[FileReadOutput]:
        workspace = context.require_resource("workspace")
        if not isinstance(workspace, WorkspaceReadService):
            raise RuntimeError("Workspace resource did not resolve to a WorkspaceReadService")
        try:
            snapshot = workspace.read_text_file(input.path)
        except WorkspaceReadError as exc:
            raise ToolInputError("无法读取该项目文件。") from exc

        content = snapshot.content[:MAX_FILE_READ_CHARS]
        output = FileReadOutput(
            path=snapshot.relative_path,
            content=content,
            content_truncated=len(snapshot.content) > MAX_FILE_READ_CHARS,
            size_bytes=snapshot.size_bytes,
            sha256=snapshot.sha256,
            readable_chars=len(snapshot.content),
        )
        artifact = ArtifactDraft(
            key="snapshot",
            type="dbfox.workspace.file_snapshot",
            schema_version=1,
            title=snapshot.relative_path,
            payload={
                "relativePath": snapshot.relative_path,
                "sizeBytes": snapshot.size_bytes,
                "sha256": snapshot.sha256,
                "truncated": snapshot.truncated,
            },
            summary=f"Read {snapshot.size_bytes} bytes from {snapshot.relative_path}",
            semantic_key=f"file_read:{snapshot.sha256}",
        )
        return ToolOutcome(output=output, artifacts=(artifact,))


class FileWritePatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(
        min_length=1,
        max_length=1_024,
        description="Workspace-relative UTF-8 text file path.",
    )
    content: str = Field(
        min_length=0,
        max_length=MAX_WORKSPACE_PATCH_CHARS,
        description="Bounded replacement file content.",
    )
    expected_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$|^$",
        description="SHA-256 of the current file; empty only when creating a file.",
    )


class FileWritePatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    old_sha256: str | None
    new_sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    created: bool


class WorkspaceFileWritePatchTool(
    BaseTool[FileWritePatchInput, FileWritePatchOutput]
):
    name = "file_write_patch"
    group = "workspace"
    description = (
        "Atomically replace a bounded UTF-8 workspace file after checking its "
        "current SHA-256. The file must remain inside the authorized Project "
        "workspace."
    )
    input_model = FileWritePatchInput
    output_model = FileWritePatchOutput
    version = "1"
    policy = ToolPolicy(risk_level="danger", requires_approval=True)
    execution = ToolExecutionSpec(
        timeout_seconds=30,
        recovery="reconcile",
        retryable=False,
        max_retries=0,
        concurrency="sequential",
        max_output_bytes=1_000_000,
        backend="isolated_process",
        capabilities=("filesystem_write",),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.workspace.code_patch",),
        contributes_progress=True,
        publishes_artifact_references=False,
    )
    presentation = ToolPresentation(
        title="修改项目文件",
        category="manage",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: FileWritePatchInput,
        context: ToolRunContext,
    ) -> ToolOutcome[FileWritePatchOutput]:
        patch_service = self._patch_service(context)
        try:
            result = patch_service.apply_patch(
                input.path,
                input.content,
                input.expected_sha256,
            )
        except WorkspacePatchConflict as exc:
            raise ToolInputError("工作区文件已发生变化，无法安全写入。") from exc
        except WorkspacePatchError as exc:
            raise ToolInputError("无法写入该项目文件。") from exc

        output = FileWritePatchOutput(
            path=result.relative_path,
            old_sha256=result.old_sha256,
            new_sha256=result.new_sha256,
            size_bytes=result.size_bytes,
            created=result.created,
        )
        artifact = ArtifactDraft(
            key="patch",
            type="dbfox.workspace.code_patch",
            schema_version=1,
            title=result.relative_path,
            payload={
                "relativePath": result.relative_path,
                "oldSha256": result.old_sha256,
                "newSha256": result.new_sha256,
                "sizeBytes": result.size_bytes,
                "created": result.created,
            },
            summary=f"Replaced {result.size_bytes} bytes in {result.relative_path}",
            semantic_key=f"file_write_patch:{result.new_sha256}",
        )
        return ToolOutcome(output=output, artifacts=(artifact,))

    def reconcile(
        self,
        input: FileWritePatchInput,
        context: ToolRunContext,
    ) -> ToolReconciliation:
        patch_service = self._patch_service(context)
        try:
            status, result = patch_service.reconcile(
                input.path,
                input.content,
                input.expected_sha256,
            )
        except WorkspacePatchError:
            return ToolReconciliation(status="unknown")
        if status == "succeeded" and result is not None:
            return ToolReconciliation(
                status="succeeded",
                output={
                    "path": result.relative_path,
                    "old_sha256": result.old_sha256,
                    "new_sha256": result.new_sha256,
                    "size_bytes": result.size_bytes,
                    "created": result.created,
                },
            )
        if status == "not_applied":
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="unknown")

    @staticmethod
    def _patch_service(context: ToolRunContext) -> WorkspacePatchService:
        workspace = context.require_resource("workspace")
        if not isinstance(workspace, WorkspaceReadService):
            raise RuntimeError(
                "Workspace resource did not resolve to a WorkspaceReadService"
            )
        return WorkspacePatchService(workspace)


class _WorkspaceFileSnapshotPayloadValidator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    relative_path: str = Field(alias="relativePath")
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    truncated: bool = False


register_artifact_payload_contract(
    "dbfox.workspace.file_snapshot",
    1,
    _WorkspaceFileSnapshotPayloadValidator,
)


class _WorkspaceCodePatchPayloadValidator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    relative_path: str = Field(alias="relativePath")
    old_sha256: str | None = Field(default=None, alias="oldSha256")
    new_sha256: str = Field(min_length=64, max_length=64, alias="newSha256")
    size_bytes: int = Field(ge=0, alias="sizeBytes")
    created: bool = False


register_artifact_payload_contract(
    "dbfox.workspace.code_patch",
    1,
    _WorkspaceCodePatchPayloadValidator,
)
