"""Tests for GitHub DLC URL normalization, boundaries, and read service."""

from __future__ import annotations

import base64
import hashlib

import httpx
import pytest

from engine.github.contracts import (
    GithubFileBinaryError,
    GithubInvalidInputError,
    GithubPrivateRepoError,
    GithubRateLimitedError,
)
from engine.github.service import (
    GithubReadService,
    normalize_github_repository,
    normalize_repository_relative_path,
    resolve_public_repository_revision,
)


def test_normalize_github_repository_valid_inputs() -> None:
    # owner/repo shorthand
    assert normalize_github_repository("facebook/react") == ("facebook", "react")
    assert normalize_github_repository("fastapi/fastapi") == ("fastapi", "fastapi")
    assert normalize_github_repository("my-org/my_repo.tools") == ("my-org", "my_repo.tools")

    # https url
    assert normalize_github_repository("https://github.com/facebook/react") == ("facebook", "react")
    assert normalize_github_repository("https://github.com/facebook/react.git") == ("facebook", "react")
    assert normalize_github_repository("http://github.com/facebook/react") == ("facebook", "react")


def test_normalize_github_repository_rejects_invalid_inputs() -> None:
    with pytest.raises(GithubInvalidInputError, match="cannot be empty"):
        normalize_github_repository("")

    with pytest.raises(GithubInvalidInputError, match="Unsupported URL scheme"):
        normalize_github_repository("ftp://github.com/foo/bar")

    with pytest.raises(GithubInvalidInputError, match="Only 'github.com' is supported"):
        normalize_github_repository("https://gitlab.com/foo/bar")

    with pytest.raises(GithubInvalidInputError, match="Only 'github.com' is supported"):
        normalize_github_repository("https://127.0.0.1/foo/bar")

    with pytest.raises(GithubInvalidInputError, match="Only 'github.com' is supported"):
        normalize_github_repository("https://localhost/foo/bar")

    with pytest.raises(GithubInvalidInputError):
        normalize_github_repository("justonepart")

    with pytest.raises(GithubInvalidInputError):
        normalize_github_repository("too/many/parts/here")


def test_normalize_repository_relative_path() -> None:
    assert normalize_repository_relative_path("") == ""
    assert normalize_repository_relative_path("src/index.ts") == "src/index.ts"
    assert normalize_repository_relative_path("/src/components/") == "src/components"
    assert normalize_repository_relative_path("src\\lib\\utils.ts") == "src/lib/utils.ts"

    with pytest.raises(GithubInvalidInputError, match="Directory traversal"):
        normalize_repository_relative_path("../secret.txt")

    with pytest.raises(GithubInvalidInputError, match="Directory traversal"):
        normalize_repository_relative_path("src/../../etc/passwd")


def test_github_read_service_overview_success() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octocat/Hello-World":
            return httpx.Response(
                200,
                json={
                    "name": "Hello-World",
                    "description": "My first repo",
                    "private": False,
                    "default_branch": "master",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    service = GithubReadService(
        owner="octocat",
        repository="Hello-World",
        revision="7fd1a60b01f91b314f59955a4e4d4e80d8edf11d",
        custom_transport=transport,
    )

    overview = service.get_repo_overview(ref_name="master")
    assert overview.owner == "octocat"
    assert overview.repository == "Hello-World"
    assert overview.resolved_revision == "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
    assert overview.default_branch == "master"
    assert overview.description == "My first repo"
    assert overview.visibility == "public"


def test_github_read_service_private_repo_rejected() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "secret-repo", "private": True})

    transport = httpx.MockTransport(mock_handler)
    service = GithubReadService(
        owner="octocat",
        repository="secret-repo",
        revision="1234567890abcdef",
        custom_transport=transport,
    )
    with pytest.raises(GithubPrivateRepoError):
        service.get_repo_overview()


def test_github_read_service_rate_limited() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})

    transport = httpx.MockTransport(mock_handler)
    service = GithubReadService(
        owner="octocat",
        repository="repo",
        revision="1234567890abcdef",
        custom_transport=transport,
    )
    with pytest.raises(GithubRateLimitedError):
        service.get_repo_overview()


def test_github_read_service_list_files() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octocat/Hello-World/contents/src":
            return httpx.Response(
                200,
                json=[
                    {"path": "src/z_file.py", "type": "file", "size": 120, "sha": "sha1"},
                    {"path": "src/components", "type": "dir", "sha": "sha2"},
                    {"path": "src/a_file.py", "type": "file", "size": 80, "sha": "sha3"},
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    service = GithubReadService(
        owner="octocat",
        repository="Hello-World",
        revision="rev123456",
        custom_transport=transport,
    )

    entries, truncated = service.list_files(path="src", limit=10)
    assert truncated is False
    assert len(entries) == 3
    # Directories sorted first, then files alphabetically
    assert entries[0].path == "src/components"
    assert entries[0].type == "dir"
    assert entries[1].path == "src/a_file.py"
    assert entries[1].type == "file"
    assert entries[2].path == "src/z_file.py"
    assert entries[2].type == "file"


def test_github_read_service_read_file_text_and_binary_rejection() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octocat/Hello-World/contents/README.md":
            content_str = "Hello DBFox GitHub DLC!"
            b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "README.md",
                    "sha": "blob_sha_123",
                    "size": len(content_str),
                    "encoding": "base64",
                    "content": b64,
                },
            )
        elif request.url.path == "/repos/octocat/Hello-World/contents/image.png":
            binary_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00"
            b64 = base64.b64encode(binary_bytes).decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "image.png",
                    "sha": "blob_sha_png",
                    "size": len(binary_bytes),
                    "encoding": "base64",
                    "content": b64,
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    service = GithubReadService(
        owner="octocat",
        repository="Hello-World",
        revision="rev_readme_123",
        custom_transport=transport,
    )

    path, rev, size, sha256, content, truncated, blob_sha = service.read_file("README.md")
    assert path == "README.md"
    assert rev == "rev_readme_123"
    assert content == "Hello DBFox GitHub DLC!"
    assert size == len("Hello DBFox GitHub DLC!")
    assert sha256 == hashlib.sha256("Hello DBFox GitHub DLC!".encode("utf-8")).hexdigest()
    assert truncated is False
    assert blob_sha == "blob_sha_123"

    # Reading binary file raises GithubFileBinaryError
    with pytest.raises(GithubFileBinaryError):
        service.read_file("image.png")


def test_resolve_public_repository_revision() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octocat/Hello-World":
            return httpx.Response(
                200,
                json={
                    "name": "Hello-World",
                    "private": False,
                    "default_branch": "main",
                    "description": "Repo description",
                },
            )
        elif request.url.path == "/repos/octocat/Hello-World/commits/main":
            return httpx.Response(
                200,
                json={"sha": "4a736a61b8f042617f1a3ec958742b6a5b9e0721"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    sha, default_branch, description = resolve_public_repository_revision(
        owner="octocat",
        repository="Hello-World",
        ref_name="main",
        custom_transport=transport,
    )
    assert sha == "4a736a61b8f042617f1a3ec958742b6a5b9e0721"
    assert default_branch == "main"
    assert description == "Repo description"
