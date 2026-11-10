from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyInput(Contract):
    pass


class WorkspaceBinding(Contract):
    id: str
    project_id: str
    root_path: str
    root_digest: str
    binding_generation: str
    created_at: str
    updated_at: str


class BindingOutput(Contract):
    binding: WorkspaceBinding | None = None


class CreateBindingInput(Contract):
    root_path: str = Field(min_length=1, max_length=4096)


class DeleteBindingOutput(Contract):
    deleted: bool


_FILE_PATH = "Path relative to the bound project root, such as src/main.py. Reuse a path returned by project search."
_DIRECTORY_PATH = "Directory relative to the bound project root. Leave empty or use . for that root."


class PathInput(Contract):
    path: str = Field(default="", max_length=1024, description=_DIRECTORY_PATH)


class FileReadInput(Contract):
    path: str = Field(min_length=1, max_length=1024, description=_FILE_PATH)
    offset: int = Field(default=0, ge=0, le=1_048_576)
    limit: int = Field(default=12_000, ge=1, le=12_000)


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
    offset: int = Field(default=0, ge=0)


class FileSearchInput(Contract):
    query: str = Field(default="", max_length=200, description="Literal case-insensitive name/path substring for recursive search; empty lists immediate children of path_prefix.")
    path_prefix: str = Field(default="", max_length=1024, description=_DIRECTORY_PATH)
    limit: int = Field(default=20, ge=1, le=100)


class FileSearchOutput(Contract):
    query: str
    path_prefix: str
    matches: list[FileEntry]
    returned_count: int = Field(ge=0)
    truncated: bool


class FileWriteInput(Contract):
    path: str = Field(min_length=1, max_length=1024, description=_FILE_PATH)
    content: str = Field(max_length=1_048_576)
    expected_sha256: str | None = Field(
        default=None, min_length=64, max_length=64,
        description="Omit only to create a new file; replacing an existing file requires its current sha256 from file_read.",
    )


class FileEditInput(Contract):
    path: str = Field(min_length=1, max_length=1024, description=_FILE_PATH)
    old_string: str = Field(min_length=1, max_length=200_000)
    new_string: str = Field(max_length=200_000)
    expected_sha256: str = Field(min_length=64, max_length=64)
    replace_all: bool = False


class FileMutationOutput(Contract):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    created: bool


class FileDeleteInput(Contract):
    path: str = Field(min_length=1, max_length=1024, description="File or empty directory relative to the bound project root.")


class FileDeleteOutput(Contract):
    path: str
    deleted: bool


class FileMoveInput(Contract):
    source_path: str = Field(min_length=1, max_length=1024, description="Existing file or directory relative to the bound project root.")
    destination_path: str = Field(min_length=1, max_length=1024, description="New path relative to the same bound project root.")


class FileMoveOutput(Contract):
    source_path: str
    destination_path: str
    moved: bool


class FileGrepInput(Contract):
    query: str = Field(min_length=1, max_length=200)
    path_prefix: str = Field(
        default="", max_length=1024,
        description="File or directory relative to the bound project root. Leave empty or use . to search the project.",
    )
    limit: int = Field(default=50, ge=1, le=100)


class FileGrepMatch(Contract):
    path: str
    line_number: int = Field(ge=1)
    line: str = Field(max_length=500)


class FileGrepOutput(Contract):
    query: str
    matches: tuple[FileGrepMatch, ...] = ()
    scanned_files: int = Field(ge=0)
    truncated: bool


CommandArgument = Annotated[str, Field(min_length=1, max_length=4096)]


class CommandRunInput(Contract):
    argv: tuple[CommandArgument, ...] = Field(min_length=1, max_length=128)
    cwd: str = Field(default="", max_length=1024, description=_DIRECTORY_PATH)
    timeout_seconds: int = Field(default=60, ge=1, le=300)

    @model_validator(mode="after")
    def reject_nul(self) -> "CommandRunInput":
        if any("\0" in value for value in self.argv):
            raise ValueError("command arguments cannot contain NUL")
        return self


class CommandRunOutput(Contract):
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int = Field(ge=0)
    output: str = Field(max_length=65_536)
    truncated: bool
    output_limit_exceeded: bool = False


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
