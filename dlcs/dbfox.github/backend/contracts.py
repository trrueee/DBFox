"""Typed contracts owned by the dbfox.github DLC."""

from __future__ import annotations

from typing import Literal

from dbfox_dlc_api import BaseModel, ConfigDict, Field, ToolInputModel, ToolOutputModel

GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE = "dbfox.github.file_snapshot"


class GithubFileSnapshotArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repositoryBindingId: str = Field(min_length=1)
    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    revision: str = Field(min_length=7, max_length=64)
    relativePath: str = Field(min_length=1, max_length=1024)
    blobSha: str = Field(min_length=1, max_length=64)
    contentSha256: str = Field(min_length=64, max_length=64)
    sizeBytes: int = Field(ge=0)
    truncated: bool = False


class GithubBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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


class GithubFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    type: Literal["file", "dir", "submodule"]
    size_bytes: int | None = None
    sha: str | None = None


class GithubRepoOverviewInput(ToolInputModel):
    pass


class GithubRepoOverviewOutput(ToolOutputModel):
    owner: str
    repository: str
    ref_name: str
    resolved_revision: str
    description: str | None = None
    default_branch: str | None = None
    visibility: str = "public"


class GithubListFilesInput(ToolInputModel):
    path: str = Field(default="", max_length=1024)
    limit: int = Field(default=50, ge=1, le=100)


class GithubListFilesOutput(ToolOutputModel):
    path: str
    revision: str
    entries: list[GithubFileEntry]
    truncated: bool = False


class GithubReadFileInput(ToolInputModel):
    path: str = Field(min_length=1, max_length=1024)


class GithubReadFileOutput(ToolOutputModel):
    path: str
    revision: str
    size_bytes: int
    content_sha256: str
    content: str
    truncated: bool = False


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListBindingsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bindings: list[GithubBinding]


class CreateBindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = Field(min_length=3, max_length=512)
    ref_name: str = Field(default="", max_length=255)


class BindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = Field(min_length=1, max_length=64)


class DeleteBindingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deleted: bool


class ListFilesOperationInput(BindingInput):
    path: str = Field(default="", max_length=1024)
    limit: int = Field(default=50, ge=1, le=100)


class ListFilesOperationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    revision: str
    entries: list[GithubFileEntry]
    truncated: bool = False


class ReadFileOperationInput(BindingInput):
    path: str = Field(min_length=1, max_length=1024)


class ReadFileOperationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    revision: str
    size_bytes: int
    content_sha256: str
    content: str
    truncated: bool = False
