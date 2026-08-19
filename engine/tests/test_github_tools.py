"""Tests for GitHub DLC tools: registration, prerequisites, execution, and artifact emission."""

from __future__ import annotations

import base64
import hashlib
import httpx

from engine.github.contracts import (
    GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
    GithubListFilesInput,
    GithubReadFileInput,
    GithubRepoOverviewInput,
)
from engine.github.service import GithubReadService
from engine.github.tools import (
    GithubListFilesTool,
    GithubReadFileTool,
    GithubRepoOverviewTool,
    register_github_extension,
)
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.context import ToolRunContext


def _mock_github_transport() -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/facebook/react":
            return httpx.Response(
                200,
                json={
                    "name": "react",
                    "private": False,
                    "default_branch": "main",
                    "description": "React UI library",
                },
            )
        elif path == "/repos/facebook/react/contents/packages":
            return httpx.Response(
                200,
                json=[
                    {"path": "packages/react", "type": "dir", "sha": "d1"},
                    {"path": "packages/README.md", "type": "file", "size": 50, "sha": "f1"},
                ],
            )
        elif path == "/repos/facebook/react/contents/package.json":
            content = '{"name": "react", "version": "19.0.0"}'
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "package.json",
                    "sha": "blob_pkg_123",
                    "size": len(content),
                    "encoding": "base64",
                    "content": b64,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_tool_registration() -> None:
    registry = ToolRegistry(available_backends=frozenset({"in_process"}))
    register_github_extension(registry)
    registry.freeze()

    assert "github_repo_overview" in registry
    assert "github_list_files" in registry
    assert "github_read_file" in registry

    overview_tool = registry.get("github_repo_overview")
    assert overview_tool.execution.required_resource_kinds == ("github.repository",)
    assert overview_tool.execution.capabilities == ("network",)

    read_tool = registry.get("github_read_file")
    assert read_tool.execution.required_resource_kinds == ("github.repository",)
    assert read_tool.execution.capabilities == ("network",)
    assert GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE in read_tool.semantics.produces


def test_github_tools_execution() -> None:
    transport = _mock_github_transport()
    service = GithubReadService(
        owner="facebook",
        repository="react",
        revision="aabbcc112233",
        binding_id="binding-react-1",
        custom_transport=transport,
    )

    context = ToolRunContext(
        idempotency_key="test-key-1",
        resources={"github.repository": service},
    )

    # 1. Test github_repo_overview
    overview_tool = GithubRepoOverviewTool()
    overview_out = overview_tool.run(GithubRepoOverviewInput(), context)
    assert overview_out.owner == "facebook"
    assert overview_out.repository == "react"
    assert overview_out.resolved_revision == "aabbcc112233"
    assert overview_out.default_branch == "main"

    # 2. Test github_list_files
    list_tool = GithubListFilesTool()
    list_out = list_tool.run(GithubListFilesInput(path="packages"), context)
    assert list_out.path == "packages"
    assert len(list_out.entries) == 2
    assert list_out.entries[0].type == "dir"
    assert list_out.entries[0].path == "packages/react"

    # 3. Test github_read_file
    read_tool = GithubReadFileTool()
    outcome = read_tool.run(GithubReadFileInput(path="package.json"), context)
    assert outcome.output.path == "package.json"
    assert outcome.output.revision == "aabbcc112233"
    assert '"name": "react"' in outcome.output.content
    assert outcome.output.content_sha256 == hashlib.sha256(
        outcome.output.content.encode("utf-8")
    ).hexdigest()

    # Artifact draft validation
    assert len(outcome.artifacts) == 1
    artifact = outcome.artifacts[0]
    assert artifact.type == GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE
    assert artifact.schema_version == 1
    assert artifact.payload["repositoryBindingId"] == "binding-react-1"
    assert artifact.payload["owner"] == "facebook"
    assert artifact.payload["repository"] == "react"
    assert artifact.payload["relativePath"] == "package.json"
    assert artifact.payload["revision"] == "aabbcc112233"
    assert artifact.payload["blobSha"] == "blob_pkg_123"
