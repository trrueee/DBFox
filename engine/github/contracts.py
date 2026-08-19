"""GitHub DLC typed contracts, schemas, artifact models, and error definitions."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from engine.agent.artifact import register_artifact_payload_contract
from engine.tools.runtime.base import ToolInputModel, ToolOutputModel

GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE = "dbfox.github.file_snapshot"


# ---------------------------------------------------------------------------
# Artifact Contracts
# ---------------------------------------------------------------------------


class GithubFileSnapshotArtifactPayload(BaseModel):
    """Artifact payload model for dbfox.github.file_snapshot v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repositoryBindingId: str = Field(min_length=1)
    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    revision: str = Field(min_length=1, max_length=64)
    relativePath: str = Field(min_length=1, max_length=1024)
    blobSha: str | None = None
    contentSha256: str = Field(min_length=1, max_length=64)
    sizeBytes: int = Field(ge=0)
    truncated: bool = False


register_artifact_payload_contract(
    GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
    1,
    GithubFileSnapshotArtifactPayload,
)


# ---------------------------------------------------------------------------
# Tool Input / Output Models
# ---------------------------------------------------------------------------


class GithubRepoOverviewInput(ToolInputModel):
    """Input model for github_repo_overview."""

    pass


class GithubRepoOverviewOutput(ToolOutputModel):
    """Output model for github_repo_overview."""

    owner: str
    repository: str
    ref_name: str
    resolved_revision: str
    description: str | None = None
    default_branch: str | None = None
    visibility: str = "public"


class GithubFileEntry(BaseModel):
    """Entry in a GitHub repository directory listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    type: Literal["file", "dir", "submodule"]
    size_bytes: int | None = None
    sha: str | None = None


class GithubListFilesInput(ToolInputModel):
    """Input model for github_list_files."""

    path: str = Field(default="", description="Repository relative directory path (e.g. 'src' or '').")
    limit: int = Field(default=50, ge=1, le=100, description="Maximum number of entries to return.")


class GithubListFilesOutput(ToolOutputModel):
    """Output model for github_list_files."""

    path: str
    revision: str
    entries: list[GithubFileEntry]
    truncated: bool = False


class GithubReadFileInput(ToolInputModel):
    """Input model for github_read_file."""

    path: str = Field(..., min_length=1, max_length=1024, description="Repository-relative path to the text file.")


class GithubReadFileOutput(ToolOutputModel):
    """Output model for github_read_file."""

    path: str
    revision: str
    size_bytes: int
    content_sha256: str
    content: str
    truncated: bool = False


# ---------------------------------------------------------------------------
# API Wire Schemas
# ---------------------------------------------------------------------------


class CreateGithubBindingRequest(BaseModel):
    """Request payload to create a new GitHub repository binding."""

    repository: str = Field(
        ...,
        description="Public GitHub repository input: 'owner/repo' or 'https://github.com/owner/repo'",
    )
    ref_name: str = Field(
        default="main",
        description="Target branch or reference name (e.g. 'main', 'master').",
    )


class GithubBindingResponse(BaseModel):
    """Response schema for a single GitHub repository binding."""

    id: str
    project_id: str
    owner: str
    repository: str
    ref_name: str
    resolved_revision: str
    default_branch: str | None = None
    description: str | None = None
    created_at: str
    updated_at: str


class GithubFileListResponse(BaseModel):
    """Response schema for repository file listing API."""

    path: str
    revision: str
    entries: list[GithubFileEntry]
    truncated: bool = False


class GithubFileContentResponse(BaseModel):
    """Response schema for repository file read API."""

    path: str
    revision: str
    size_bytes: int
    content_sha256: str
    content: str
    truncated: bool = False


# ---------------------------------------------------------------------------
# Error Definitions
# ---------------------------------------------------------------------------


class GithubServiceError(Exception):
    """Base exception for all GitHub DLC service errors."""

    code: str = "GITHUB_SERVICE_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class GithubNotFoundError(GithubServiceError):
    code = "GITHUB_REPOSITORY_NOT_FOUND"


class GithubPrivateRepoError(GithubServiceError):
    code = "GITHUB_PRIVATE_REPO_UNSUPPORTED"


class GithubRevisionUnavailableError(GithubServiceError):
    code = "GITHUB_REVISION_UNAVAILABLE"


class GithubFileNotFoundError(GithubServiceError):
    code = "GITHUB_FILE_NOT_FOUND"


class GithubFileBinaryError(GithubServiceError):
    code = "GITHUB_FILE_BINARY"


class GithubFileTooLargeError(GithubServiceError):
    code = "GITHUB_FILE_TOO_LARGE"


class GithubRateLimitedError(GithubServiceError):
    code = "GITHUB_RATE_LIMITED"


class GithubNetworkUnavailableError(GithubServiceError):
    code = "GITHUB_NETWORK_UNAVAILABLE"


class GithubInvalidInputError(GithubServiceError):
    code = "GITHUB_INVALID_INPUT"
