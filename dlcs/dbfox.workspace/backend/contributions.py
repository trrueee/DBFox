from __future__ import annotations

from dbfox_dlc_api import (
    ArtifactDraft,
    BackendExtensionHost,
    BaseTool,
    CapabilityGuidanceSpec,
    ContextContributionInput,
    ContextFragment,
    DlcOperationContext,
    DlcOperationError,
    DlcOperationSpec,
    ExtensionToolRunContext,
    ResourceScopeRef,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputError,
    ToolOutcome,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
    ToolKey,
)

from .contracts import (
    BindingOutput,
    CommandRunInput,
    CommandRunOutput,
    CreateBindingInput,
    DeleteBindingOutput,
    EmptyInput,
    FileEntry,
    FileDeleteInput,
    FileDeleteOutput,
    FileEditInput,
    FileGrepInput,
    FileGrepMatch,
    FileGrepOutput,
    FileListOutput,
    FileMoveInput,
    FileMoveOutput,
    FileMutationOutput,
    FileReadInput,
    FileReadOutput,
    FileSearchInput,
    FileSearchOutput,
    FileWriteInput,
    PathInput,
    WorkspaceBinding,
    WorkspaceCodePatchPayload,
    WorkspaceFileSnapshotPayload,
)
from .service import (
    WorkspaceConflict,
    WorkspaceError,
    WorkspaceService,
)
from .store import WORKSPACE_RESOURCE_KIND, WorkspaceBindingStore
from .representation import FILE_REPRESENTATION, WorkspaceFileRepresentation

FILE_SNAPSHOT = "dbfox.workspace.file_snapshot"
CODE_PATCH = "dbfox.workspace.code_patch"
MAX_CONTEXT_CHARS = 3_600


def _workspace(context: ExtensionToolRunContext) -> WorkspaceService:
    resource = context.require_one(WORKSPACE_RESOURCE_KIND)
    if not isinstance(resource, WorkspaceService):
        raise RuntimeError("workspace did not resolve to WorkspaceService")
    return resource


def _scope(context: ExtensionToolRunContext) -> ResourceScopeRef:
    refs = context.scopes(WORKSPACE_RESOURCE_KIND)
    if len(refs) != 1:
        raise RuntimeError("Workspace tool requires exactly one workspace scope")
    return refs[0]


class WorkspaceFileSearchTool(BaseTool[FileSearchInput, FileSearchOutput]):
    name = "file_search"
    group = "workspace"
    description = (
        "Find files and directories recursively by a literal name or relative-path substring. "
        "An empty query lists immediate children of path_prefix. Skips dependency/build folders; "
        "truncated means the bounded scan or result limit was reached."
    )
    input_model = FileSearchInput
    output_model = FileSearchOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.file_search",))
    presentation = ToolPresentation(title="搜索项目文件", category="explore")

    def run(self, input: FileSearchInput, context: ExtensionToolRunContext) -> FileSearchOutput:
        try:
            directory = _workspace(context).search_files(input.query, path_prefix=input.path_prefix, limit=input.limit)
        except WorkspaceError as exc:
            raise ToolInputError("无法读取该项目文件夹。") from exc
        matches = directory.entries
        return FileSearchOutput(
            query=input.query,
            path_prefix=input.path_prefix,
            matches=[
                FileEntry(name=item.name, path=item.relative_path, is_dir=item.is_dir)
                for item in matches
            ],
            returned_count=len(matches),
            truncated=directory.truncated,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目文件搜索失败。")
        matches = list(output.get("matches") or [])
        provider_matches = matches[:20]
        return ToolObservationProjection(
            summary=f"已找到 {int(output.get('returned_count') or 0)} 个项目文件。",
            facts={
                "query": output.get("query"),
                "path_prefix": output.get("path_prefix"),
                "returned_count": output.get("returned_count"),
                "truncated": output.get("truncated"),
            },
            provider_payload={
                **output,
                "matches": provider_matches,
                "truncated": (
                    bool(output.get("truncated"))
                    or len(matches) > len(provider_matches)
                ),
            },
        )


class WorkspaceFileReadTool(BaseTool[FileReadInput, FileReadOutput]):
    name = "file_read"
    group = "workspace"
    description = "Read one bounded UTF-8 file from the authorized local workspace."
    input_model = FileReadInput
    output_model = FileReadOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=1_000_000,
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=(FILE_SNAPSHOT,))
    presentation = ToolPresentation(title="读取项目文件", category="explore")

    def run(self, input: FileReadInput, context: ExtensionToolRunContext) -> ToolOutcome[FileReadOutput]:
        try:
            snapshot = _workspace(context).read_text_file(input.path)
        except WorkspaceError as exc:
            raise ToolInputError("无法读取该项目文件。") from exc
        workspace_ref = _scope(context)
        workspace_id = str(workspace_ref.id)
        workspace_version = str(workspace_ref.version or "")
        content = snapshot.content[input.offset : input.offset + input.limit]
        output = FileReadOutput(
            path=snapshot.relative_path,
            content=content,
            content_truncated=(
                snapshot.truncated
                or input.offset + len(content) < len(snapshot.content)
            ),
            size_bytes=snapshot.size_bytes,
            sha256=snapshot.sha256,
            offset=input.offset,
        )
        return ToolOutcome(
            output=output,
            artifacts=(ArtifactDraft(
                key="snapshot",
                type=FILE_SNAPSHOT,
                schema_version=1,
                title=snapshot.relative_path,
                payload={
                    "relativePath": snapshot.relative_path,
                    "sizeBytes": snapshot.size_bytes,
                    "sha256": snapshot.sha256,
                    "truncated": snapshot.truncated,
                    "workspaceId": workspace_id,
                    "workspaceVersion": workspace_version,
                },
                summary=f"Read {snapshot.size_bytes} bytes from {snapshot.relative_path}",
                semantic_key=f"file_read:{snapshot.sha256}",
                resource_refs=(workspace_ref,),
            ),),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目文件读取失败。")
        return ToolObservationProjection(
            summary=f"已读取项目文件 {str(output.get('path') or '')}。",
            facts={
                "path": output.get("path"),
                "content_truncated": output.get("content_truncated"),
                "size_bytes": output.get("size_bytes"),
                "sha256": output.get("sha256"),
            },
            provider_payload=output,
        )


def _mutation_output(snapshot, *, created: bool) -> FileMutationOutput:
    return FileMutationOutput(
        path=snapshot.relative_path,
        size_bytes=snapshot.size_bytes,
        sha256=snapshot.sha256,
        created=created,
    )


def _patch_outcome(
    output: FileMutationOutput,
    *,
    workspace_ref: ResourceScopeRef,
    old_sha256: str | None,
) -> ToolOutcome[FileMutationOutput]:
    return ToolOutcome(
        output=output,
        artifacts=(ArtifactDraft(
            key="patch",
            type=CODE_PATCH,
            schema_version=1,
            title=output.path,
            payload={
                "relativePath": output.path,
                "oldSha256": old_sha256,
                "newSha256": output.sha256,
                "sizeBytes": output.size_bytes,
                "created": output.created,
                "workspaceId": str(workspace_ref.id),
                "workspaceVersion": str(workspace_ref.version or ""),
            },
            summary=f"Updated {output.path}",
            semantic_key=f"file_patch:{output.sha256}",
            resource_refs=(workspace_ref,),
        ),),
    )


class WorkspaceFileWriteTool(BaseTool[FileWriteInput, FileMutationOutput]):
    name = "file_write"
    group = "workspace"
    description = (
        "Create a UTF-8 text file or replace a previously read file inside the "
        "authorized workspace. Existing files require their current sha256."
    )
    input_model = FileWriteInput
    output_model = FileMutationOutput
    version = "2"
    policy = ToolPolicy(risk_level="warning", requires_approval=True)
    execution = ToolExecutionSpec(
        backend="isolated_process",
        timeout_seconds=30,
        recovery="never_retry",
        capabilities=("filesystem_write",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=(CODE_PATCH, "dbfox.workspace.file_write"))
    presentation = ToolPresentation(title="写入项目文件", category="manage")

    def run(self, input: FileWriteInput, context: ExtensionToolRunContext):
        workspace = _workspace(context)
        try:
            snapshot = workspace.write_text_file(
                input.path,
                input.content,
                expected_sha256=input.expected_sha256,
            )
        except WorkspaceConflict as exc:
            raise ToolInputError(str(exc)) from exc
        except WorkspaceError as exc:
            raise ToolInputError("无法写入该项目文件。") from exc
        return _patch_outcome(
            _mutation_output(snapshot, created=input.expected_sha256 is None),
            workspace_ref=_scope(context),
            old_sha256=input.expected_sha256,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目文件写入失败。")
        return ToolObservationProjection(
            summary=f"已写入项目文件 {output['path']}。",
            facts={key: output[key] for key in ("path", "size_bytes", "sha256", "created")},
        )


class WorkspaceFileEditTool(BaseTool[FileEditInput, FileMutationOutput]):
    name = "file_edit"
    group = "workspace"
    description = (
        "Edit a previously read UTF-8 file by exact string replacement. The "
        "old string must be unique unless replace_all is true, and sha256 must match."
    )
    input_model = FileEditInput
    output_model = FileMutationOutput
    version = "2"
    policy = ToolPolicy(risk_level="warning", requires_approval=True)
    execution = ToolExecutionSpec(
        backend="isolated_process",
        timeout_seconds=30,
        recovery="never_retry",
        capabilities=("filesystem_write",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=(CODE_PATCH, "dbfox.workspace.file_edit"))
    presentation = ToolPresentation(title="编辑项目文件", category="manage")

    def run(self, input: FileEditInput, context: ExtensionToolRunContext):
        try:
            snapshot = _workspace(context).edit_text_file(
                input.path,
                old_string=input.old_string,
                new_string=input.new_string,
                expected_sha256=input.expected_sha256,
                replace_all=input.replace_all,
            )
        except WorkspaceConflict as exc:
            raise ToolInputError(str(exc)) from exc
        except WorkspaceError as exc:
            raise ToolInputError("无法精确编辑该项目文件，请重新读取并使用唯一锚点。") from exc
        return _patch_outcome(
            _mutation_output(snapshot, created=False),
            workspace_ref=_scope(context),
            old_sha256=input.expected_sha256,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目文件编辑失败。")
        return ToolObservationProjection(
            summary=f"已精确编辑项目文件 {output['path']}。",
            facts={key: output[key] for key in ("path", "size_bytes", "sha256")},
        )


class WorkspaceFileDeleteTool(BaseTool[FileDeleteInput, FileDeleteOutput]):
    name = "file_delete"
    group = "workspace"
    description = "Delete one file or empty directory inside the authorized workspace."
    input_model = FileDeleteInput
    output_model = FileDeleteOutput
    version = "1"
    policy = ToolPolicy(risk_level="danger", requires_approval=True)
    execution = ToolExecutionSpec(
        backend="isolated_process",
        timeout_seconds=30,
        recovery="never_retry",
        capabilities=("filesystem_write",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.file_delete",))
    presentation = ToolPresentation(title="删除项目路径", category="manage")

    def run(self, input: FileDeleteInput, context: ExtensionToolRunContext):
        try:
            _workspace(context).delete_path(input.path)
        except WorkspaceError as exc:
            raise ToolInputError("无法删除该项目路径。") from exc
        return FileDeleteOutput(path=WorkspaceService.normalize(input.path), deleted=True)


class WorkspaceFileMoveTool(BaseTool[FileMoveInput, FileMoveOutput]):
    name = "file_move"
    group = "workspace"
    description = "Move or rename one path inside the authorized workspace without overwrite."
    input_model = FileMoveInput
    output_model = FileMoveOutput
    version = "2"
    policy = ToolPolicy(risk_level="warning", requires_approval=True)
    execution = ToolExecutionSpec(
        backend="isolated_process",
        timeout_seconds=30,
        recovery="never_retry",
        capabilities=("filesystem_write",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.file_move",))
    presentation = ToolPresentation(title="移动项目路径", category="manage")

    def run(self, input: FileMoveInput, context: ExtensionToolRunContext):
        try:
            _workspace(context).move_path(input.source_path, input.destination_path)
        except WorkspaceConflict as exc:
            raise ToolInputError(str(exc)) from exc
        except WorkspaceError as exc:
            raise ToolInputError("无法移动该项目路径。") from exc
        return FileMoveOutput(
            source_path=WorkspaceService.normalize(input.source_path),
            destination_path=WorkspaceService.normalize(input.destination_path),
            moved=True,
        )


class WorkspaceFileGrepTool(BaseTool[FileGrepInput, FileGrepOutput]):
    name = "file_grep"
    group = "workspace"
    description = "Search literal text recursively across bounded UTF-8 workspace files."
    input_model = FileGrepInput
    output_model = FileGrepOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.file_grep",))
    presentation = ToolPresentation(title="搜索项目内容", category="explore")

    def run(self, input: FileGrepInput, context: ExtensionToolRunContext):
        try:
            result = _workspace(context).grep_text_files(
                input.query,
                path_prefix=input.path_prefix,
                limit=input.limit,
            )
        except WorkspaceError as exc:
            raise ToolInputError("无法搜索项目文件内容。") from exc
        return FileGrepOutput(
            query=input.query,
            matches=tuple(FileGrepMatch(
                path=match.relative_path,
                line_number=match.line_number,
                line=match.line,
            ) for match in result.matches),
            scanned_files=result.scanned_files,
            truncated=result.truncated,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目内容搜索失败。")
        return ToolObservationProjection(
            summary=f"已找到 {len(output['matches'])} 个项目内容匹配。",
            facts={"scanned_files": output["scanned_files"], "truncated": output["truncated"]},
            provider_payload=output,
        )


class WorkspaceCommandRunTool(BaseTool[CommandRunInput, CommandRunOutput]):
    name = "command_run"
    group = "workspace"
    description = (
        "Run one executable with an argv array in the authorized workspace. "
        "No shell is used; cwd stays inside the workspace; output and time are bounded."
    )
    input_model = CommandRunInput
    output_model = CommandRunOutput
    version = "1"
    policy = ToolPolicy(risk_level="danger", requires_approval=True)
    execution = ToolExecutionSpec(
        backend="isolated_process",
        timeout_seconds=330,
        recovery="never_retry",
        max_output_bytes=128_000,
        capabilities=("subprocess",),
        required_resources=(ToolResourceRequirement(kind=WORKSPACE_RESOURCE_KIND),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.command_result",))
    presentation = ToolPresentation(title="运行项目命令", category="manage")

    def run(self, input: CommandRunInput, context: ExtensionToolRunContext):
        try:
            result = _workspace(context).run_command(
                input.argv,
                cwd=input.cwd,
                timeout_seconds=input.timeout_seconds,
            )
        except WorkspaceError as exc:
            raise ToolInputError("无法在项目工作区运行该命令。") from exc
        return CommandRunOutput(
            argv=result.argv,
            cwd=result.cwd,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            duration_ms=result.duration_ms,
            output=result.output,
            truncated=result.truncated,
            output_limit_exceeded=result.output_limit_exceeded,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="项目命令执行失败。")
        return ToolObservationProjection(
            summary=(
                "项目命令输出超过硬上限，已终止。"
                if output["output_limit_exceeded"]
                else "项目命令已超时。" if output["timed_out"] else
                f"项目命令已结束，退出码 {output['exit_code']}。"
            ),
            facts={
                "argv": output["argv"],
                "cwd": output["cwd"],
                "exit_code": output["exit_code"],
                "timed_out": output["timed_out"],
                "duration_ms": output["duration_ms"],
                "truncated": output["truncated"],
                "output_limit_exceeded": output["output_limit_exceeded"],
            },
            provider_payload=output,
        )


class WorkspaceContextContributor:
    id = "dbfox.workspace"

    def __init__(self, store: WorkspaceBindingStore) -> None:
        self._store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        authorized = {
            (str(ref.id), str(ref.version or ""))
            for ref in input.resource_refs
            if ref.kind == WORKSPACE_RESOURCE_KIND
        }
        fragments: list[ContextFragment] = []
        for observation in input.recent_artifacts:
            if observation.artifact_type != FILE_SNAPSHOT:
                continue
            payload = observation.payload
            artifact_workspace_refs = tuple(
                ref for ref in observation.resource_refs if ref.kind == WORKSPACE_RESOURCE_KIND
            )
            identity = (
                (
                    str(artifact_workspace_refs[0].id),
                    str(artifact_workspace_refs[0].version or ""),
                )
                if len(artifact_workspace_refs) == 1
                else (
                    str(payload.get("workspaceId") or ""),
                    str(payload.get("workspaceVersion") or ""),
                )
            )
            if identity not in authorized:
                continue
            try:
                workspace = self._store.resolve(next(
                    ref for ref in input.resource_refs
                    if ref.kind == WORKSPACE_RESOURCE_KIND and (str(ref.id), str(ref.version or "")) == identity
                ))
                snapshot = workspace.read_text_file(str(payload.get("relativePath") or ""))
            except (WorkspaceError, ValueError, StopIteration):
                continue
            if snapshot.sha256 != str(payload.get("sha256") or ""):
                continue
            fragments.append(ContextFragment(
                source_id="dbfox.workspace",
                source_version=observation.observation_id,
                lane="resource",
                content=(
                    f"workspace file snapshot: {snapshot.relative_path}\n"
                    f"sha256: {snapshot.sha256}\ncontent:\n{snapshot.content[:MAX_CONTEXT_CHARS]}"
                ),
                provenance={
                    "artifact_id": observation.artifact_id,
                    "observation_id": observation.observation_id,
                    "relative_path": snapshot.relative_path,
                    "content_truncated": len(snapshot.content) > MAX_CONTEXT_CHARS,
                },
            ))
            if len(fragments) >= 8:
                break
        return tuple(fragments)


def _project_id(context: DlcOperationContext) -> str:
    if not context.project_id:
        raise ValueError("Workspace operation requires a project_id")
    return context.project_id


def _operation_error(message: str, *, code: str = "WORKSPACE_INVALID", status: int = 400) -> DlcOperationError:
    return DlcOperationError(code=code, message=message, status_code=status)


def _register_operations(host: BackendExtensionHost, store: WorkspaceBindingStore) -> None:
    def project_workspace(context: DlcOperationContext) -> WorkspaceService:
        binding = store.get_project_binding(_project_id(context))
        if binding is None:
            raise _operation_error("Workspace binding not found", code="WORKSPACE_NOT_FOUND", status=404)
        return WorkspaceService(binding.root_path, mutation_database=store.database_path)

    def get_binding(_input: EmptyInput, context: DlcOperationContext) -> BindingOutput:
        return BindingOutput(binding=store.get_project_binding(_project_id(context)))

    def create_binding(input: CreateBindingInput, context: DlcOperationContext) -> WorkspaceBinding:
        try:
            return store.create_binding(_project_id(context), input.root_path)
        except WorkspaceError as exc:
            raise _operation_error("The selected workspace folder is unavailable") from exc
        except ValueError as exc:
            raise _operation_error(str(exc), code="WORKSPACE_BINDING_CONFLICT", status=409) from exc

    def delete_binding(_input: EmptyInput, context: DlcOperationContext) -> DeleteBindingOutput:
        return DeleteBindingOutput(deleted=store.delete_binding(_project_id(context)))

    def list_files(input: PathInput, context: DlcOperationContext) -> FileListOutput:
        try:
            directory = project_workspace(context).list_directory(input.path)
        except WorkspaceError as exc:
            raise _operation_error("Workspace directory cannot be read") from exc
        return FileListOutput(
            path=WorkspaceService.normalize(input.path),
            entries=[
                FileEntry(name=e.name, path=e.relative_path, is_dir=e.is_dir)
                for e in directory.entries
            ],
            truncated=directory.truncated,
        )

    def read_file(input: FileReadInput, context: DlcOperationContext) -> FileReadOutput:
        try:
            snapshot = project_workspace(context).read_text_file(input.path)
        except WorkspaceError as exc:
            raise _operation_error("Workspace file cannot be read") from exc
        content = snapshot.content[input.offset : input.offset + input.limit]
        return FileReadOutput(
            path=snapshot.relative_path,
            content=content,
            content_truncated=(
                snapshot.truncated
                or input.offset + len(content) < len(snapshot.content)
            ),
            size_bytes=snapshot.size_bytes,
            sha256=snapshot.sha256,
            offset=input.offset,
        )

    def write_file(input: FileWriteInput, context: DlcOperationContext) -> FileMutationOutput:
        workspace = project_workspace(context)
        try:
            snapshot = workspace.write_text_file(
                input.path,
                input.content,
                expected_sha256=input.expected_sha256,
            )
        except WorkspaceConflict as exc:
            raise _operation_error(str(exc), code="WORKSPACE_CONFLICT", status=409) from exc
        except WorkspaceError as exc:
            raise _operation_error("Workspace file cannot be written") from exc
        return _mutation_output(snapshot, created=input.expected_sha256 is None)

    def edit_file(input: FileEditInput, context: DlcOperationContext) -> FileMutationOutput:
        try:
            snapshot = project_workspace(context).edit_text_file(
                input.path,
                old_string=input.old_string,
                new_string=input.new_string,
                expected_sha256=input.expected_sha256,
                replace_all=input.replace_all,
            )
        except WorkspaceConflict as exc:
            raise _operation_error(str(exc), code="WORKSPACE_CONFLICT", status=409) from exc
        except WorkspaceError as exc:
            raise _operation_error("Workspace file cannot be edited") from exc
        return _mutation_output(snapshot, created=False)

    def delete_file(input: FileDeleteInput, context: DlcOperationContext) -> FileDeleteOutput:
        try:
            project_workspace(context).delete_path(input.path)
        except WorkspaceError as exc:
            raise _operation_error("Workspace path cannot be deleted") from exc
        return FileDeleteOutput(path=WorkspaceService.normalize(input.path), deleted=True)

    def move_file(input: FileMoveInput, context: DlcOperationContext) -> FileMoveOutput:
        try:
            project_workspace(context).move_path(input.source_path, input.destination_path)
        except WorkspaceConflict as exc:
            raise _operation_error(str(exc), code="WORKSPACE_CONFLICT", status=409) from exc
        except WorkspaceError as exc:
            raise _operation_error("Workspace path cannot be moved") from exc
        return FileMoveOutput(
            source_path=WorkspaceService.normalize(input.source_path),
            destination_path=WorkspaceService.normalize(input.destination_path),
            moved=True,
        )

    def grep_files(input: FileGrepInput, context: DlcOperationContext) -> FileGrepOutput:
        try:
            result = project_workspace(context).grep_text_files(
                input.query,
                path_prefix=input.path_prefix,
                limit=input.limit,
            )
        except WorkspaceError as exc:
            raise _operation_error("Workspace files cannot be searched") from exc
        return FileGrepOutput(
            query=input.query,
            matches=tuple(FileGrepMatch(
                path=match.relative_path,
                line_number=match.line_number,
                line=match.line,
            ) for match in result.matches),
            scanned_files=result.scanned_files,
            truncated=result.truncated,
        )

    for spec in (
        DlcOperationSpec(name="binding.get", input_model=EmptyInput, output_model=BindingOutput, handler=get_binding, scope="project"),
        DlcOperationSpec(name="binding.create", input_model=CreateBindingInput, output_model=WorkspaceBinding, handler=create_binding, scope="project", capabilities=("filesystem_read",)),
        DlcOperationSpec(name="binding.delete", input_model=EmptyInput, output_model=DeleteBindingOutput, handler=delete_binding, scope="project"),
        DlcOperationSpec(name="files.list", input_model=PathInput, output_model=FileListOutput, handler=list_files, scope="project", capabilities=("filesystem_read",)),
        DlcOperationSpec(name="files.read", input_model=FileReadInput, output_model=FileReadOutput, handler=read_file, scope="project", capabilities=("filesystem_read",)),
        DlcOperationSpec(name="files.write", input_model=FileWriteInput, output_model=FileMutationOutput, handler=write_file, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="files.edit", input_model=FileEditInput, output_model=FileMutationOutput, handler=edit_file, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="files.delete", input_model=FileDeleteInput, output_model=FileDeleteOutput, handler=delete_file, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="files.move", input_model=FileMoveInput, output_model=FileMoveOutput, handler=move_file, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="files.grep", input_model=FileGrepInput, output_model=FileGrepOutput, handler=grep_files, scope="project", capabilities=("filesystem_read",)),
    ):
        host.operations.register(spec)


def register(host: BackendExtensionHost) -> None:
    store = WorkspaceBindingStore(host.runtime_info.data_path)
    host.tools.register(WorkspaceFileSearchTool())
    host.tools.register(WorkspaceFileReadTool())
    host.tools.register(WorkspaceFileWriteTool())
    host.tools.register(WorkspaceFileEditTool())
    host.tools.register(WorkspaceFileDeleteTool())
    host.tools.register(WorkspaceFileMoveTool())
    host.tools.register(WorkspaceFileGrepTool())
    host.tools.register(WorkspaceCommandRunTool())
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(WORKSPACE_RESOURCE_KIND, store.resolve)
    host.context.register(WorkspaceContextContributor(store))
    host.agent_guidance.register(CapabilityGuidanceSpec(
        id="workspace_evidence", version="1",
        applies_to_resource_kinds=(WORKSPACE_RESOURCE_KIND,),
        applies_to_artifact_types=(FILE_SNAPSHOT, CODE_PATCH),
        tool_refs=tuple(ToolKey(owner_id="dbfox.workspace", local_name=name) for name in (
            "file_search", "file_read", "file_write", "file_edit", "file_grep", "command_run",
        )),
        instructions=(
            "Distinguish a file's assertions, static code review, saved changes, and observed execution. "
            "A document saying completed or a successful file write does not prove a feature works. "
            "Report verification as unverified unless supported by available execution evidence, and state its scope. "
            "Never turn a search with no matches or a truncated listing into proof that the entire project lacks a file, test, or implementation. "
            "Use file_search with a nonempty literal name/path query for bounded recursive discovery, or an empty query to list direct children. "
            "Read the required remaining file pages before concluding from truncated content. "
            "Do not repeat an interrupted mutation or command until its outcome is verified; a rejection is not authorization to resubmit it."
        ),
    ))
    host.artifacts.register(FILE_SNAPSHOT, 1, WorkspaceFileSnapshotPayload)
    host.artifacts.register(CODE_PATCH, 1, WorkspaceCodePatchPayload)
    for artifact_type in (FILE_SNAPSHOT, CODE_PATCH):
        host.artifacts.register_representation(artifact_type, FILE_REPRESENTATION, WorkspaceFileRepresentation(store))
    _register_operations(host, store)
