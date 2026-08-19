"""Tool contracts and implementations for dbfox.github."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.errors import ToolInputError
from engine.github.contracts import (
    GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
    GithubFileBinaryError,
    GithubFileNotFoundError,
    GithubFileTooLargeError,
    GithubInvalidInputError,
    GithubListFilesInput,
    GithubListFilesOutput,
    GithubNetworkUnavailableError,
    GithubNotFoundError,
    GithubPrivateRepoError,
    GithubRateLimitedError,
    GithubReadFileInput,
    GithubReadFileOutput,
    GithubRepoOverviewInput,
    GithubRepoOverviewOutput,
    GithubServiceError,
)
from engine.agent.artifact import ArtifactDraft
from engine.github.service import GithubReadService
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolOutcome,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)
from engine.tools.runtime.context import ToolRunContext

if TYPE_CHECKING:
    from engine.tools.runtime import ToolRegistry


class GithubRepoOverviewTool(BaseTool[GithubRepoOverviewInput, GithubRepoOverviewOutput]):
    name = "github_repo_overview"
    group = "github"
    description = "Get metadata and overview of the connected GitHub repository at its authorized revision."
    input_model = GithubRepoOverviewInput
    output_model = GithubRepoOverviewOutput
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
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.github.repo_overview",),
        contributes_progress=True,
    )
    presentation = ToolPresentation(
        title="读取仓库概况",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: GithubRepoOverviewInput,
        context: ToolRunContext,
    ) -> GithubRepoOverviewOutput:
        del input
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("Resource 'github.repository' did not resolve to GithubReadService")
        try:
            return service.get_repo_overview()
        except GithubNotFoundError as exc:
            raise ToolInputError(f"GitHub repository '{service.owner}/{service.repository}' not found.") from exc
        except GithubPrivateRepoError as exc:
            raise ToolInputError("Private repositories are not supported.") from exc
        except GithubRateLimitedError as exc:
            raise ToolInputError("GitHub API rate limit reached.") from exc
        except GithubNetworkUnavailableError as exc:
            raise ToolInputError("GitHub network is unavailable.") from exc
        except GithubServiceError as exc:
            raise ToolInputError(f"GitHub error: {exc}") from exc


class GithubListFilesTool(BaseTool[GithubListFilesInput, GithubListFilesOutput]):
    name = "github_list_files"
    group = "github"
    description = "List directory contents and files within the GitHub repository at the authorized revision."
    input_model = GithubListFilesInput
    output_model = GithubListFilesOutput
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
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.github.file_list",),
        contributes_progress=True,
    )
    presentation = ToolPresentation(
        title="浏览仓库文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: GithubListFilesInput,
        context: ToolRunContext,
    ) -> GithubListFilesOutput:
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("Resource 'github.repository' did not resolve to GithubReadService")
        try:
            entries, truncated = service.list_files(input.path, input.limit)
            return GithubListFilesOutput(
                path=input.path,
                revision=service.revision,
                entries=entries,
                truncated=truncated,
            )
        except GithubInvalidInputError as exc:
            raise ToolInputError(str(exc)) from exc
        except GithubNotFoundError as exc:
            raise ToolInputError(f"Directory '{input.path}' not found on GitHub.") from exc
        except GithubRateLimitedError as exc:
            raise ToolInputError("GitHub API rate limit reached.") from exc
        except GithubNetworkUnavailableError as exc:
            raise ToolInputError("GitHub network is unavailable.") from exc
        except GithubServiceError as exc:
            raise ToolInputError(f"GitHub error: {exc}") from exc


class GithubReadFileTool(BaseTool[GithubReadFileInput, GithubReadFileOutput]):
    name = "github_read_file"
    group = "github"
    description = "Read a text file from the GitHub repository at the exact authorized revision and produce a file snapshot artifact."
    input_model = GithubReadFileInput
    output_model = GithubReadFileOutput
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
        capabilities=("network",),
        required_resource_kinds=("github.repository",),
    )
    semantics = ToolSemanticSpec(
        produces=(GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,),
        contributes_progress=True,
    )
    presentation = ToolPresentation(
        title="读取仓库文件",
        category="explore",
        visibility="summary",
        progress="indeterminate",
    )

    def run(
        self,
        input: GithubReadFileInput,
        context: ToolRunContext,
    ) -> ToolOutcome[GithubReadFileOutput]:
        service = context.require_resource("github.repository")
        if not isinstance(service, GithubReadService):
            raise RuntimeError("Resource 'github.repository' did not resolve to GithubReadService")
        try:
            norm_path, rev, size, sha256, content, truncated, blob_sha = service.read_file(input.path)
        except GithubInvalidInputError as exc:
            raise ToolInputError(str(exc)) from exc
        except GithubFileNotFoundError as exc:
            raise ToolInputError(f"File '{input.path}' not found at revision {service.revision[:7]}.") from exc
        except GithubFileBinaryError as exc:
            raise ToolInputError(f"Cannot read binary file '{input.path}' as text.") from exc
        except GithubFileTooLargeError as exc:
            raise ToolInputError(f"File '{input.path}' is too large to read.") from exc
        except GithubRateLimitedError as exc:
            raise ToolInputError("GitHub API rate limit reached.") from exc
        except GithubNetworkUnavailableError as exc:
            raise ToolInputError("GitHub network is unavailable.") from exc
        except GithubServiceError as exc:
            raise ToolInputError(f"GitHub error: {exc}") from exc

        output = GithubReadFileOutput(
            path=norm_path,
            revision=rev,
            size_bytes=size,
            content_sha256=sha256,
            content=content,
            truncated=truncated,
        )

        artifact = ArtifactDraft(
            key="github_file_snapshot",
            type=GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
            schema_version=1,
            title=f"GitHub: {service.owner}/{service.repository} - {norm_path}",
            payload={
                "repositoryBindingId": service.binding_id,
                "owner": service.owner,
                "repository": service.repository,
                "revision": rev,
                "relativePath": norm_path,
                "blobSha": blob_sha,
                "contentSha256": sha256,
                "sizeBytes": size,
                "truncated": truncated,
            },
            summary=f"Read {norm_path} at revision {rev[:7]}",
        )

        return ToolOutcome(output=output, artifacts=(artifact,))


GITHUB_OWNER = "dbfox.github"


def register_github_extension(registry: ToolRegistry) -> None:
    """Register the GitHub tool suite with the central product registry."""
    registry.register(GithubRepoOverviewTool(), owner=GITHUB_OWNER)
    registry.register(GithubListFilesTool(), owner=GITHUB_OWNER)
    registry.register(GithubReadFileTool(), owner=GITHUB_OWNER)
