"""Tests for GitHub DLC repository binding persistence and resource provider/resolver."""

from __future__ import annotations

import httpx
import pytest

from engine.github.contracts import GithubInvalidInputError
from engine.github.models import GithubRepositoryBinding
from engine.github.repository import (
    create_github_binding,
    delete_github_binding,
    get_github_binding,
    list_github_bindings,
    refresh_github_binding,
)
from engine.github.resource import list_github_resources, resolve_github_repository
from engine.models import Project
from engine.tools.runtime.attempt import ResourceScopeRef


def _mock_github_transport() -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/facebook/react":
            return httpx.Response(
                200,
                json={
                    "name": "react",
                    "private": False,
                    "default_branch": "main",
                    "description": "The library for web and native user interfaces",
                },
            )
        elif request.url.path == "/repos/facebook/react/commits/main":
            return httpx.Response(
                200,
                json={"sha": "e91c3da45831964177d465d6c8b9db1a2b3c4d5e"},
            )
        elif request.url.path == "/repos/facebook/react/commits/v18.0.0":
            return httpx.Response(
                200,
                json={"sha": "1818181818181818181818181818181818181818"},
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_repository_binding_crud(db_session) -> None:
    project = Project(id="proj-gh-1", name="GitHub Project 1")
    db_session.add(project)
    db_session.commit()

    transport = _mock_github_transport()

    # 1. Create binding
    binding = create_github_binding(
        db=db_session,
        project_id="proj-gh-1",
        repo_input="facebook/react",
        ref_name="main",
        custom_transport=transport,
    )
    assert binding.id is not None
    assert binding.owner == "facebook"
    assert binding.repository == "react"
    assert binding.ref_name == "main"
    assert binding.resolved_revision == "e91c3da45831964177d465d6c8b9db1a2b3c4d5e"
    assert binding.default_branch == "main"

    # 2. Get binding
    fetched = get_github_binding(db_session, binding.id)
    assert fetched is not None
    assert fetched.id == binding.id

    # 3. List bindings
    bindings = list_github_bindings(db_session, "proj-gh-1")
    assert len(bindings) == 1
    assert bindings[0].id == binding.id

    # 4. Refresh binding
    refreshed = refresh_github_binding(db_session, binding.id, custom_transport=transport)
    assert refreshed.resolved_revision == "e91c3da45831964177d465d6c8b9db1a2b3c4d5e"

    # 5. Duplicate rejection
    with pytest.raises(GithubInvalidInputError, match="already exists"):
        create_github_binding(
            db=db_session,
            project_id="proj-gh-1",
            repo_input="https://github.com/facebook/react",
            ref_name="main",
            custom_transport=transport,
        )

    # 6. Delete binding
    assert delete_github_binding(db_session, binding.id) is True
    assert get_github_binding(db_session, binding.id) is None
    assert len(list_github_bindings(db_session, "proj-gh-1")) == 0


def test_github_resource_provider_discovery(db_session) -> None:
    project_id = "proj-provider-test"
    db_session.add(Project(id=project_id, name="Provider Test"))
    db_session.flush()
    db_session.add(
        GithubRepositoryBinding(
            id="bind-1",
            project_id=project_id,
            owner="fastapi",
            repository="fastapi",
            ref_name="master",
            resolved_revision="11223344556677889900aabbccddeeff00112233",
        )
    )
    db_session.commit()

    descriptors = list_github_resources(db_session, project_id)
    assert len(descriptors) == 1
    assert descriptors[0].kind == "github.repository"
    assert descriptors[0].id == "bind-1"
    assert descriptors[0].version == "11223344556677889900aabbccddeeff00112233"
    assert descriptors[0].name == "fastapi/fastapi"


def test_github_resource_resolver_freshness_and_stale_fence(db_session) -> None:
    project_id = "proj-resolver-test"
    db_session.add(Project(id=project_id, name="Resolver Test"))
    db_session.flush()
    db_session.add(
        GithubRepositoryBinding(
            id="bind-valid",
            project_id=project_id,
            owner="pallets",
            repository="flask",
            ref_name="main",
            resolved_revision="aabbccddeeff0011223344556677889900aabbcc",
        )
    )
    db_session.commit()

    # Successful resolution with matching revision
    valid_ref = ResourceScopeRef(
        kind="github.repository",
        id="bind-valid",
        version="aabbccddeeff0011223344556677889900aabbcc",
    )
    service = resolve_github_repository(db_session, valid_ref)
    assert service.owner == "pallets"
    assert service.repository == "flask"
    assert service.revision == "aabbccddeeff0011223344556677889900aabbcc"
    assert service.binding_id == "bind-valid"

    # Stale revision rejection (raises ValueError)
    stale_ref = ResourceScopeRef(
        kind="github.repository",
        id="bind-valid",
        version="old_revision_123456",
    )
    with pytest.raises(ValueError, match="does not match authorized execution scope"):
        resolve_github_repository(db_session, stale_ref)

    # Missing binding rejection
    missing_ref = ResourceScopeRef(
        kind="github.repository",
        id="bind-nonexistent",
        version="aabbccddeeff",
    )
    with pytest.raises(ValueError, match="does not exist"):
        resolve_github_repository(db_session, missing_ref)
