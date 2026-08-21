"""Tests for GitHub DLC repository binding persistence and resource provider/resolver."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from engine.github.contracts import GithubInvalidInputError
from engine.github.migration import GithubBindingRecord, transitional_store
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

    # 2. Get binding scoped to project
    fetched = get_github_binding(db_session, "proj-gh-1", binding.id)
    assert fetched is not None
    assert fetched.id == binding.id

    # 3. Foreign project lookup returns None
    assert get_github_binding(db_session, "foreign-proj", binding.id) is None

    # 4. List bindings
    bindings = list_github_bindings(db_session, "proj-gh-1")
    assert len(bindings) == 1
    assert bindings[0].id == binding.id

    # 5. Refresh binding
    refreshed = refresh_github_binding(db_session, "proj-gh-1", binding.id, custom_transport=transport)
    assert refreshed.resolved_revision == "e91c3da45831964177d465d6c8b9db1a2b3c4d5e"

    # 6. Duplicate rejection
    with pytest.raises(GithubInvalidInputError, match="already exists"):
        create_github_binding(
            db=db_session,
            project_id="proj-gh-1",
            repo_input="https://github.com/facebook/react",
            ref_name="main",
            custom_transport=transport,
        )

    # 7. Delete binding (fails closed on foreign project)
    assert delete_github_binding(db_session, "foreign-proj", binding.id) is False
    assert delete_github_binding(db_session, "proj-gh-1", binding.id) is True
    assert get_github_binding(db_session, "proj-gh-1", binding.id) is None
    assert len(list_github_bindings(db_session, "proj-gh-1")) == 0


def test_cross_project_binding_isolation_fails_closed(db_session) -> None:
    p1 = Project(id="proj-alpha", name="Project Alpha")
    p2 = Project(id="proj-beta", name="Project Beta")
    db_session.add_all([p1, p2])
    db_session.commit()

    transport = _mock_github_transport()

    binding_alpha = create_github_binding(
        db=db_session,
        project_id="proj-alpha",
        repo_input="facebook/react",
        ref_name="main",
        custom_transport=transport,
    )

    # Project Beta cannot read, refresh, or delete Alpha's binding
    assert get_github_binding(db_session, "proj-beta", binding_alpha.id) is None
    with pytest.raises(Exception):
        refresh_github_binding(db_session, "proj-beta", binding_alpha.id, custom_transport=transport)
    assert delete_github_binding(db_session, "proj-beta", binding_alpha.id) is False

    # Alpha's binding remains unharmed
    assert get_github_binding(db_session, "proj-alpha", binding_alpha.id) is not None


def test_default_branch_resolution_when_ref_name_empty(db_session) -> None:
    project = Project(id="proj-default-branch", name="Default Branch Project")
    db_session.add(project)
    db_session.commit()

    def mock_default_branch_transport() -> httpx.BaseTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/astral-sh/uv":
                return httpx.Response(
                    200,
                    json={
                        "name": "uv",
                        "private": False,
                        "default_branch": "main",
                        "description": "Fast Python package manager",
                    },
                )
            elif request.url.path == "/repos/astral-sh/uv/commits/main":
                return httpx.Response(
                    200,
                    json={"sha": "4444555566667777888899990000111122223333"},
                )
            return httpx.Response(404)

        return httpx.MockTransport(handler)

    binding = create_github_binding(
        db=db_session,
        project_id="proj-default-branch",
        repo_input="astral-sh/uv",
        ref_name="",  # empty ref_name must auto-discover default_branch
        custom_transport=mock_default_branch_transport(),
    )
    assert binding.ref_name == "main"
    assert binding.default_branch == "main"
    assert binding.resolved_revision == "4444555566667777888899990000111122223333"


def test_github_resource_provider_discovery(db_session) -> None:
    project_id = "proj-provider-test"
    db_session.add(Project(id=project_id, name="Provider Test"))
    db_session.flush()
    db_session.commit()
    transitional_store(db_session).create_binding(
        GithubBindingRecord(
            id="bind-1",
            project_id=project_id,
            owner="fastapi",
            repository="fastapi",
            ref_name="master",
            resolved_revision="11223344556677889900aabbccddeeff00112233",
            default_branch=None,
            description=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )

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
    db_session.commit()
    transitional_store(db_session).create_binding(
        GithubBindingRecord(
            id="bind-valid",
            project_id=project_id,
            owner="pallets",
            repository="flask",
            ref_name="main",
            resolved_revision="aabbccddeeff0011223344556677889900aabbcc",
            default_branch=None,
            description=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )

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
    assert service.ref_name == "main"

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
