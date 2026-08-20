"""Backend contributions registered by the dbfox.github DLC."""

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
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .contracts import (
    BindingInput,
    CreateBindingInput,
    DeleteBindingOutput,
    EmptyInput,
    GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
    GithubBinding,
    GithubFileSnapshotArtifactPayload,
    GithubListFilesInput,
    GithubListFilesOutput,
    GithubReadFileInput,
    GithubReadFileOutput,
    GithubRepoOverviewInput,
    GithubRepoOverviewOutput,
    ListBindingsOutput,
    ListFilesOperationInput,
    ListFilesOperationOutput,
    ReadFileOperationInput,
    ReadFileOperationOutput,
)
from .service import (
    GithubFileBinaryError,
    GithubFileTooLargeError,
    GithubInvalidInputError,
    GithubNetworkUnavailableError,
    GithubNotFoundError,
    GithubPrivateRepoError,
    GithubRateLimitedError,
    GithubReadService,
    GithubServiceError,
    normalize_github_repository,
    resolve_public_repository_revision,
)
from .store import GithubBindingStore

MAX_GITHUB_CONTEXT_FILES = 4
MAX_CHARS_PER_FILE = 4_000
MAX_TOTAL_CONTEXT_CHARS = 12_000


def _read_service(store: GithubBindingStore, ref: ResourceScopeRef) -> GithubReadService:
    binding = store.resolve(ref)
    return GithubReadService(
        owner=binding.owner,
        repository=binding.repository,
        revision=binding.resolved_revision,
        binding_id=binding.id,
        ref_name=binding.ref_name,
    )


def _tool_error(exc: GithubServiceError) -> ToolInputError:
    if isinstance(exc, GithubPrivateRepoError):
        return ToolInputError("Private GitHub repositories are not supported")
    if isinstance(exc, GithubRateLimitedError):
        return ToolInputError("GitHub API rate limit reached")
    if isinstance(exc, GithubNetworkUnavailableError):
        return ToolInputError("GitHub network is unavailable")
    return ToolInputError(str(exc))


def _operation_error(exc: GithubServiceError) -> DlcOperationError:
    if isinstance(exc, GithubInvalidInputError):
        return DlcOperationError(code="GITHUB_INVALID_INPUT", message=str(exc), status_code=400)
    if isinstance(exc, GithubNotFoundError):
        return DlcOperationError(code="GITHUB_NOT_FOUND", message=str(exc), status_code=404)
    if isinstance(exc, GithubPrivateRepoError):
        return DlcOperationError(
            code="GITHUB_PRIVATE_REPOSITORY",
            message="Private GitHub repositories are not supported",
            status_code=400,
        )
    if isinstance(exc, GithubRateLimitedError):
        return DlcOperationError(code="GITHUB_RATE_LIMITED", message=str(exc), status_code=429)
    if isinstance(exc, GithubNetworkUnavailableError):
        return DlcOperationError(
            code="GITHUB_NETWORK_UNAVAILABLE",
            message="GitHub API is temporarily unreachable",
            status_code=502,
        )
    return DlcOperationError(code="GITHUB_API_ERROR", message=str(exc), status_code=502)


class GithubRepoOverviewTool(BaseTool[GithubRepoOverviewInput, GithubRepoOverviewOutput]):
    name = "github_repo_overview"
    group = "github"
    description = "Get public repository metadata at the exact authorized GitHub revision."
    input_model = GithubRepoOverviewInput
    output_model = GithubRepoOverviewOutput
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.github.repo_overview",))
    presentation = ToolPresentation(
        title="读取仓库概况",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        tool_input: GithubRepoOverviewInput,
        context: ExtensionToolRunContext,
    ) -> GithubRepoOverviewOutput:
        del tool_input
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("github.repository did not resolve to GithubReadService")
        try:
            return service.get_repo_overview()
        except GithubServiceError as exc:
            raise _tool_error(exc) from exc


class GithubListFilesTool(BaseTool[GithubListFilesInput, GithubListFilesOutput]):
    name = "github_list_files"
    group = "github"
    description = "List files in a public GitHub repository at its authorized revision."
    input_model = GithubListFilesInput
    output_model = GithubListFilesOutput
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.github.file_list",))
    presentation = ToolPresentation(
        title="浏览仓库文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        tool_input: GithubListFilesInput,
        context: ExtensionToolRunContext,
    ) -> GithubListFilesOutput:
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("github.repository did not resolve to GithubReadService")
        try:
            entries, truncated = service.list_files(tool_input.path, tool_input.limit)
        except GithubServiceError as exc:
            raise _tool_error(exc) from exc
        return GithubListFilesOutput(
            path=tool_input.path,
            revision=service.revision,
            entries=entries,
            truncated=truncated,
        )


class GithubReadFileTool(BaseTool[GithubReadFileInput, GithubReadFileOutput]):
    name = "github_read_file"
    group = "github"
    description = "Read a public GitHub text file at the authorized revision."
    input_model = GithubReadFileInput
    output_model = GithubReadFileOutput
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=200_000,
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(produces=(GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,))
    presentation = ToolPresentation(
        title="读取仓库文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        tool_input: GithubReadFileInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[GithubReadFileOutput]:
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("github.repository did not resolve to GithubReadService")
        try:
            path, revision, size, digest, content, truncated, blob_sha = service.read_file(
                tool_input.path
            )
        except (
            GithubInvalidInputError,
            GithubNotFoundError,
            GithubFileBinaryError,
            GithubFileTooLargeError,
            GithubServiceError,
        ) as exc:
            raise _tool_error(exc) from exc
        output = GithubReadFileOutput(
            path=path,
            revision=revision,
            size_bytes=size,
            content_sha256=digest,
            content=content,
            truncated=truncated,
        )
        artifact = ArtifactDraft(
            key="github_file_snapshot",
            type=GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
            schema_version=1,
            title=f"GitHub: {service.owner}/{service.repository} - {path}",
            payload={
                "repositoryBindingId": service.binding_id,
                "owner": service.owner,
                "repository": service.repository,
                "revision": revision,
                "relativePath": path,
                "blobSha": blob_sha,
                "contentSha256": digest,
                "sizeBytes": size,
                "truncated": truncated,
            },
            summary=f"Read {path} at revision {revision[:7]}",
        )
        return ToolOutcome(output=output, artifacts=(artifact,))


class GithubContextContributor:
    id = "dbfox.github"

    def __init__(self, store: GithubBindingStore) -> None:
        self._store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        authorized = {
            str(ref.id): str(ref.version or "")
            for ref in input.resource_refs
            if ref.kind == "github.repository"
        }
        if not authorized:
            return ()

        fragments: list[ContextFragment] = []
        seen: set[tuple[str, str]] = set()
        total_chars = 0
        for observation in input.recent_artifacts:
            if observation.artifact_type != GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE:
                continue
            payload = observation.payload
            binding_id = str(payload.get("repositoryBindingId") or "")
            revision = str(payload.get("revision") or "")
            relative_path = str(payload.get("relativePath") or "")
            expected_digest = str(payload.get("contentSha256") or "")
            if authorized.get(binding_id) != revision or not relative_path or not expected_digest:
                continue
            key = (binding_id, relative_path)
            if key in seen:
                continue
            try:
                service = _read_service(
                    self._store,
                    ResourceScopeRef(
                        kind="github.repository",
                        id=binding_id,
                        version=revision,
                    ),
                )
                _path, _revision, _size, digest, content, _truncated, _blob = (
                    service.read_file(relative_path)
                )
            except (GithubServiceError, ValueError, KeyError):
                continue
            if digest != expected_digest:
                continue
            seen.add(key)
            bounded = content[:MAX_CHARS_PER_FILE]
            remaining = MAX_TOTAL_CONTEXT_CHARS - total_chars
            if remaining <= 0:
                break
            bounded = bounded[:remaining]
            total_chars += len(bounded)
            fragments.append(
                ContextFragment(
                    source_id="dbfox.github",
                    source_version=observation.observation_id,
                    lane="resource",
                    content=(
                        f"github file snapshot: {service.owner}/{service.repository} @ {revision[:7]}\n"
                        f"path: {relative_path}\nsha256: {digest}\ncontent:\n{bounded}"
                    ),
                    provenance={
                        "artifact_id": observation.artifact_id,
                        "observation_id": observation.observation_id,
                        "binding_id": binding_id,
                        "relative_path": relative_path,
                        "revision": revision,
                        "content_truncated": len(content) > len(bounded),
                    },
                )
            )
            if len(fragments) >= MAX_GITHUB_CONTEXT_FILES:
                break
        return tuple(fragments)


def _project_id(context: DlcOperationContext) -> str:
    if not context.project_id:
        raise ValueError("This GitHub operation requires a project_id")
    return context.project_id


def _service_for_project_binding(
    store: GithubBindingStore,
    project_id: str,
    binding_id: str,
) -> tuple[GithubBinding, GithubReadService]:
    binding = store.get_project_binding(project_id, binding_id)
    if binding is None:
        raise DlcOperationError(
            code="GITHUB_BINDING_NOT_FOUND",
            message=f"GitHub binding not found: {binding_id}",
            status_code=404,
        )
    return binding, GithubReadService(
        owner=binding.owner,
        repository=binding.repository,
        revision=binding.resolved_revision,
        binding_id=binding.id,
        ref_name=binding.ref_name,
    )


def _register_operations(host: BackendExtensionHost, store: GithubBindingStore) -> None:
    def list_bindings(_input: EmptyInput, context: DlcOperationContext) -> ListBindingsOutput:
        return ListBindingsOutput(bindings=store.list_bindings(_project_id(context)))

    def create_binding(input: CreateBindingInput, context: DlcOperationContext) -> GithubBinding:
        project_id = _project_id(context)
        try:
            owner, repository = normalize_github_repository(input.repository)
            revision, ref_name, default_branch, description = resolve_public_repository_revision(
                owner,
                repository,
                input.ref_name,
            )
            return store.create_binding(
                project_id=project_id,
                owner=owner,
                repository=repository,
                ref_name=ref_name,
                resolved_revision=revision,
                default_branch=default_branch,
                description=description,
            )
        except GithubServiceError as exc:
            raise _operation_error(exc) from exc
        except ValueError as exc:
            raise DlcOperationError(
                code="GITHUB_BINDING_CONFLICT",
                message=str(exc),
                status_code=409,
            ) from exc

    def delete_binding(input: BindingInput, context: DlcOperationContext) -> DeleteBindingOutput:
        if not store.delete_binding(_project_id(context), input.binding_id):
            raise DlcOperationError(
                code="GITHUB_BINDING_NOT_FOUND",
                message=f"GitHub binding not found: {input.binding_id}",
                status_code=404,
            )
        return DeleteBindingOutput(deleted=True)

    def refresh_binding(input: BindingInput, context: DlcOperationContext) -> GithubBinding:
        binding, _service = _service_for_project_binding(
            store,
            _project_id(context),
            input.binding_id,
        )
        try:
            revision, ref_name, default_branch, description = resolve_public_repository_revision(
                binding.owner,
                binding.repository,
                binding.ref_name,
            )
        except GithubServiceError as exc:
            raise _operation_error(exc) from exc
        return store.update_binding(
            binding.id,
            ref_name=ref_name,
            resolved_revision=revision,
            default_branch=default_branch,
            description=description,
        )

    def list_files(
        input: ListFilesOperationInput,
        context: DlcOperationContext,
    ) -> ListFilesOperationOutput:
        _binding, service = _service_for_project_binding(
            store,
            _project_id(context),
            input.binding_id,
        )
        try:
            entries, truncated = service.list_files(input.path, input.limit)
        except GithubServiceError as exc:
            raise _operation_error(exc) from exc
        return ListFilesOperationOutput(
            path=input.path,
            revision=service.revision,
            entries=entries,
            truncated=truncated,
        )

    def read_file(
        input: ReadFileOperationInput,
        context: DlcOperationContext,
    ) -> ReadFileOperationOutput:
        _binding, service = _service_for_project_binding(
            store,
            _project_id(context),
            input.binding_id,
        )
        try:
            path, revision, size, digest, content, truncated, _blob = service.read_file(
                input.path
            )
        except GithubServiceError as exc:
            raise _operation_error(exc) from exc
        return ReadFileOperationOutput(
            path=path,
            revision=revision,
            size_bytes=size,
            content_sha256=digest,
            content=content,
            truncated=truncated,
        )

    specs: tuple[DlcOperationSpec, ...] = (
        DlcOperationSpec(
            name="bindings.list",
            input_model=EmptyInput,
            output_model=ListBindingsOutput,
            handler=list_bindings,
            scope="project",
        ),
        DlcOperationSpec(
            name="bindings.create",
            input_model=CreateBindingInput,
            output_model=GithubBinding,
            handler=create_binding,
            scope="project",
            capabilities=("network",),
        ),
        DlcOperationSpec(
            name="bindings.delete",
            input_model=BindingInput,
            output_model=DeleteBindingOutput,
            handler=delete_binding,
            scope="project",
        ),
        DlcOperationSpec(
            name="bindings.refresh",
            input_model=BindingInput,
            output_model=GithubBinding,
            handler=refresh_binding,
            scope="project",
            capabilities=("network",),
        ),
        DlcOperationSpec(
            name="files.list",
            input_model=ListFilesOperationInput,
            output_model=ListFilesOperationOutput,
            handler=list_files,
            scope="project",
            capabilities=("network",),
        ),
        DlcOperationSpec(
            name="files.read",
            input_model=ReadFileOperationInput,
            output_model=ReadFileOperationOutput,
            handler=read_file,
            scope="project",
            capabilities=("network",),
        ),
    )
    for spec in specs:
        host.operations.register(spec)


def register(host: BackendExtensionHost) -> None:
    store = GithubBindingStore(host.runtime_info.data_path)
    host.tools.register(GithubRepoOverviewTool())
    host.tools.register(GithubListFilesTool())
    host.tools.register(GithubReadFileTool())
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(
        "github.repository",
        lambda ref: _read_service(store, ref),
    )
    host.context.register(GithubContextContributor(store))
    host.artifacts.register(
        GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
        1,
        GithubFileSnapshotArtifactPayload,
    )
    _register_operations(host, store)
