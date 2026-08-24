from __future__ import annotations

from dbfox_dlc_api import (
    ArtifactDraft,
    BackendExtensionHost,
    BaseTool,
    ContextContributionInput,
    ContextFragment,
    DlcOperationContext,
    DlcOperationError,
    DlcOperationSpec,
    ExtensionToolRunContext,
    ResourceScopeRef,
    ToolExecutionSpec,
    ToolInputError,
    ToolOutcome,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .contracts import (
    BindingOutput,
    CreateBindingInput,
    DeleteBindingOutput,
    EmptyInput,
    FileEntry,
    FileListOutput,
    FileReadInput,
    FileReadOutput,
    FileSearchInput,
    FileSearchOutput,
    PathInput,
    WorkspaceBinding,
    WorkspaceCodePatchPayload,
    WorkspaceFileSnapshotPayload,
)
from .service import (
    WorkspaceError,
    WorkspaceService,
)
from .store import WORKSPACE_RESOURCE_KIND, WorkspaceBindingStore

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
    description = "Search bounded file names inside the authorized local workspace."
    input_model = FileSearchInput
    output_model = FileSearchOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        capabilities=("filesystem_read",),
        required_resource_kinds=(WORKSPACE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.workspace.file_search",))
    presentation = ToolPresentation(title="搜索项目文件", category="explore")

    def run(self, input: FileSearchInput, context: ExtensionToolRunContext) -> FileSearchOutput:
        try:
            entries = _workspace(context).list_directory(input.path_prefix)
        except WorkspaceError as exc:
            raise ToolInputError("无法读取该项目文件夹。") from exc
        needle = input.query.casefold()
        all_matches = [entry for entry in entries if needle in entry.name.casefold()]
        matches = all_matches[: input.limit]
        return FileSearchOutput(
            query=input.query,
            path_prefix=input.path_prefix,
            matches=[
                FileEntry(name=item.name, path=item.relative_path, is_dir=item.is_dir)
                for item in matches
            ],
            returned_count=len(matches),
            truncated=len(all_matches) > len(matches),
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
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=1_000_000,
        capabilities=("filesystem_read",),
        required_resource_kinds=(WORKSPACE_RESOURCE_KIND,),
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
        content = snapshot.content[:12_000]
        output = FileReadOutput(
            path=snapshot.relative_path,
            content=content,
            content_truncated=len(snapshot.content) > len(content),
            size_bytes=snapshot.size_bytes,
            sha256=snapshot.sha256,
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
        binding = store.get_project_binding(_project_id(context))
        if binding is None:
            raise _operation_error("Workspace binding not found", code="WORKSPACE_NOT_FOUND", status=404)
        try:
            entries = WorkspaceService(binding.root_path).list_directory(input.path)
        except WorkspaceError as exc:
            raise _operation_error("Workspace directory cannot be read") from exc
        return FileListOutput(
            path=WorkspaceService.normalize(input.path),
            entries=[FileEntry(name=e.name, path=e.relative_path, is_dir=e.is_dir) for e in entries],
        )

    def read_file(input: FileReadInput, context: DlcOperationContext) -> FileReadOutput:
        binding = store.get_project_binding(_project_id(context))
        if binding is None:
            raise _operation_error("Workspace binding not found", code="WORKSPACE_NOT_FOUND", status=404)
        try:
            snapshot = WorkspaceService(binding.root_path).read_text_file(input.path)
        except WorkspaceError as exc:
            raise _operation_error("Workspace file cannot be read") from exc
        content = snapshot.content[:12_000]
        return FileReadOutput(
            path=snapshot.relative_path,
            content=content,
            content_truncated=len(snapshot.content) > len(content),
            size_bytes=snapshot.size_bytes,
            sha256=snapshot.sha256,
        )

    for spec in (
        DlcOperationSpec(name="binding.get", input_model=EmptyInput, output_model=BindingOutput, handler=get_binding, scope="project"),
        DlcOperationSpec(name="binding.create", input_model=CreateBindingInput, output_model=WorkspaceBinding, handler=create_binding, scope="project", capabilities=("filesystem_read",)),
        DlcOperationSpec(name="binding.delete", input_model=EmptyInput, output_model=DeleteBindingOutput, handler=delete_binding, scope="project"),
        DlcOperationSpec(name="files.list", input_model=PathInput, output_model=FileListOutput, handler=list_files, scope="project", capabilities=("filesystem_read",)),
        DlcOperationSpec(name="files.read", input_model=FileReadInput, output_model=FileReadOutput, handler=read_file, scope="project", capabilities=("filesystem_read",)),
    ):
        host.operations.register(spec)


def register(host: BackendExtensionHost) -> None:
    store = WorkspaceBindingStore(host.runtime_info.data_path)
    host.tools.register(WorkspaceFileSearchTool())
    host.tools.register(WorkspaceFileReadTool())
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(WORKSPACE_RESOURCE_KIND, store.resolve)
    host.context.register(WorkspaceContextContributor(store))
    host.artifacts.register(FILE_SNAPSHOT, 1, WorkspaceFileSnapshotPayload)
    host.artifacts.register(CODE_PATCH, 1, WorkspaceCodePatchPayload)
    _register_operations(host, store)
