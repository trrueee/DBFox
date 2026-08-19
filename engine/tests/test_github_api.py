"""Tests for GitHub DLC FastAPI routes and project isolation fencing."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from engine.github.api import (
    create_binding,
    delete_binding_route,
    get_bindings,
    list_binding_files,
    read_binding_file,
    refresh_binding_route,
)
from engine.github.contracts import CreateGithubBindingRequest
from engine.models import Project


def _mock_github_transport() -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/owner-a/repo-a":
            return httpx.Response(
                200,
                json={
                    "name": "repo-a",
                    "private": False,
                    "default_branch": "main",
                    "description": "Repo A description",
                },
            )
        elif path == "/repos/owner-a/repo-a/commits/main":
            return httpx.Response(
                200,
                json={"sha": "1111222233334444555566667777888899990000"},
            )
        elif path == "/repos/owner-a/repo-a/contents/":
            return httpx.Response(
                200,
                json=[{"path": "README.md", "type": "file", "size": 14, "sha": "blob1"}],
            )
        elif path == "/repos/owner-a/repo-a/contents/README.md":
            import base64
            b64 = base64.b64encode(b"# Repo A Hello").decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "README.md",
                    "sha": "blob1",
                    "size": 14,
                    "encoding": "base64",
                    "content": b64,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_api_project_fencing_and_crud(db_session, monkeypatch) -> None:
    # 1. Setup two distinct projects
    p1 = Project(id="proj-fence-1", name="Project 1")
    p2 = Project(id="proj-fence-2", name="Project 2")
    db_session.add_all([p1, p2])
    db_session.commit()

    # Monkeypatch transport for repository resolver
    transport = _mock_github_transport()
    from engine.github import repository as repo_module
    orig_resolve = repo_module.resolve_public_repository_revision

    def patched_resolve(owner, repository, ref_name="", **kwargs):
        return orig_resolve(owner, repository, ref_name=ref_name, custom_transport=transport)

    monkeypatch.setattr(repo_module, "resolve_public_repository_revision", patched_resolve)

    # Monkeypatch transport in GithubReadService
    from engine.github import service as service_module

    def patched_get_client(self):
        return httpx.Client(
            base_url="https://api.github.com",
            transport=transport,
        )

    monkeypatch.setattr(service_module.GithubReadService, "_get_client", patched_get_client)

    # 2. Create binding in Project 1 with empty ref_name (auto default branch)
    created = create_binding(
        project_id="proj-fence-1",
        req=CreateGithubBindingRequest(repository="owner-a/repo-a", ref_name=""),
        db=db_session,
    )
    assert created.id is not None
    assert created.project_id == "proj-fence-1"
    assert created.ref_name == "main"
    assert created.resolved_revision == "1111222233334444555566667777888899990000"

    binding_id = created.id

    # 3. List bindings in Project 1 vs Project 2
    b1_list = get_bindings(project_id="proj-fence-1", db=db_session)
    assert len(b1_list) == 1
    assert b1_list[0].id == binding_id

    b2_list = get_bindings(project_id="proj-fence-2", db=db_session)
    assert len(b2_list) == 0

    # 4. Cross-project file listing -> 404
    with pytest.raises(HTTPException) as exc_info:
        list_binding_files(project_id="proj-fence-2", binding_id=binding_id, path="", limit=50, db=db_session)
    assert exc_info.value.status_code == 404

    # Valid project file listing -> 200
    files = list_binding_files(project_id="proj-fence-1", binding_id=binding_id, path="", limit=50, db=db_session)
    assert len(files.entries) == 1
    assert files.entries[0].path == "README.md"

    # 5. Cross-project file read -> 404
    with pytest.raises(HTTPException) as exc_info:
        read_binding_file(project_id="proj-fence-2", binding_id=binding_id, path="README.md", db=db_session)
    assert exc_info.value.status_code == 404

    # Valid project file read -> 200
    file_content = read_binding_file(project_id="proj-fence-1", binding_id=binding_id, path="README.md", db=db_session)
    assert file_content.content == "# Repo A Hello"

    # 6. Cross-project refresh -> 404
    with pytest.raises(HTTPException) as exc_info:
        refresh_binding_route(project_id="proj-fence-2", binding_id=binding_id, db=db_session)
    assert exc_info.value.status_code == 404

    # Valid project refresh -> 200
    refreshed = refresh_binding_route(project_id="proj-fence-1", binding_id=binding_id, db=db_session)
    assert refreshed.id == binding_id

    # 7. Cross-project delete -> 404
    with pytest.raises(HTTPException) as exc_info:
        delete_binding_route(project_id="proj-fence-2", binding_id=binding_id, db=db_session)
    assert exc_info.value.status_code == 404

    # Binding still exists in Project 1
    assert len(get_bindings(project_id="proj-fence-1", db=db_session)) == 1

    # 8. Valid project delete -> 204
    delete_binding_route(project_id="proj-fence-1", binding_id=binding_id, db=db_session)
    assert len(get_bindings(project_id="proj-fence-1", db=db_session)) == 0
