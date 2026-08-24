from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyInput(Contract):
    pass


class WorkspaceBinding(Contract):
    id: str
    project_id: str
    root_path: str
    root_digest: str
    created_at: str
    updated_at: str


class BindingOutput(Contract):
    binding: WorkspaceBinding | None = None


class CreateBindingInput(Contract):
    root_path: str = Field(min_length=1, max_length=4096)


class DeleteBindingOutput(Contract):
    deleted: bool


class PathInput(Contract):
    path: str = Field(default="", max_length=1024)


class FileReadInput(Contract):
    path: str = Field(min_length=1, max_length=1024)


class FileEntry(Contract):
    name: str
    path: str
    is_dir: bool


class FileListOutput(Contract):
    path: str
    entries: list[FileEntry]
    truncated: bool = False


class FileReadOutput(Contract):
    path: str
    content: str = Field(max_length=12_000)
    content_truncated: bool
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class FileSearchInput(Contract):
    query: str = Field(min_length=1, max_length=200)
    path_prefix: str = Field(default="", max_length=1024)
    limit: int = Field(default=20, ge=1, le=100)


class FileSearchOutput(Contract):
    query: str
    path_prefix: str
    matches: list[FileEntry]
    returned_count: int = Field(ge=0)
    truncated: bool


class WorkspaceFileSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    relative_path: str = Field(alias="relativePath")
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    truncated: bool = False
    workspace_id: str = Field(alias="workspaceId")
    workspace_version: str = Field(alias="workspaceVersion")


class WorkspaceCodePatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    relative_path: str = Field(alias="relativePath")
    old_sha256: str | None = Field(default=None, alias="oldSha256")
    new_sha256: str = Field(min_length=64, max_length=64, alias="newSha256")
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    created: bool
    workspace_id: str = Field(alias="workspaceId")
    workspace_version: str = Field(alias="workspaceVersion")
