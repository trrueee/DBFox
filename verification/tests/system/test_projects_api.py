from __future__ import annotations

import uuid
import pytest
from fastapi import HTTPException

from engine.api.projects import api_create_project, api_list_project_resources, api_list_projects
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.models import DEFAULT_PROJECT_ID, Project
from engine.runtime_composition import set_active_runtime_snapshot
from engine.schemas import ProjectCreateRequest
from engine.projects.service import resolve_project_id


def test_project_id_resolution_fallback_creates_default_project(db_session) -> None:
    assert resolve_project_id(db_session, None) == DEFAULT_PROJECT_ID
    assert resolve_project_id(db_session, "") == DEFAULT_PROJECT_ID
    assert resolve_project_id(db_session, DEFAULT_PROJECT_ID) == DEFAULT_PROJECT_ID

    project = db_session.get(Project, DEFAULT_PROJECT_ID)
    assert project is not None
    assert project.status == "active"


def test_create_project_persists_only_project_identity_and_metadata(db_session) -> None:
    result = api_create_project(
        ProjectCreateRequest(
            name="  订单分析  ",
            description="  desc  ",
        ),
        db_session,
    )

    assert result["name"] == "订单分析"
    assert result["description"] == "desc"
    assert "workspace_root" not in result

    persisted = db_session.get(Project, result["id"])
    assert persisted is not None
    assert "workspace_root" not in Project.__table__.columns


def test_reopening_folder_registration_does_not_duplicate_project(db_session) -> None:
    request = ProjectCreateRequest(name="workspace", idempotency_key="folder:canonical-digest")
    first = api_create_project(request, db_session)
    second = api_create_project(request, db_session)
    assert second["id"] == first["id"]
    assert db_session.query(Project).filter(Project.id == first["id"]).count() == 1
    assert "idempotency_key" not in second


def test_project_creation_key_rejects_a_different_payload(db_session) -> None:
    api_create_project(ProjectCreateRequest(name="workspace", idempotency_key="same-key"), db_session)
    with pytest.raises(HTTPException) as conflict:
        api_create_project(ProjectCreateRequest(name="other", idempotency_key="same-key"), db_session)
    assert conflict.value.status_code == 409
    assert db_session.query(Project).filter(Project.name == "other").count() == 0


def test_project_without_creation_key_remains_a_separate_identity(db_session) -> None:
    first = api_create_project(ProjectCreateRequest(name="same name"), db_session)
    second = api_create_project(ProjectCreateRequest(name="same name"), db_session)
    assert first["id"] != second["id"]


def test_concurrent_folder_registration_has_one_project(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 'projects.sqlite3'}")
    Project.__table__.create(engine)

    def create(_index):
        with Session(engine) as session:
            return api_create_project(ProjectCreateRequest(name="workspace", idempotency_key="concurrent-folder"), session)["id"]

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(create, range(8)))
        assert len(set(identifiers)) == 1
        with Session(engine) as session:
            assert session.query(Project).count() == 1
    finally:
        engine.dispose()


def test_list_projects_returns_only_active_project_metadata(db_session) -> None:
    project_a = Project(id=str(uuid.uuid4()), name="Project A", status="active")
    project_b = Project(id=str(uuid.uuid4()), name="Project B", status="active")
    inactive = Project(id=str(uuid.uuid4()), name="Inactive", status="archived")
    db_session.add_all([project_a, project_b, inactive])
    db_session.commit()

    result = api_list_projects(db_session)

    by_id = {item["id"]: item for item in result}
    assert "datasource_count" not in by_id[project_a.id]
    assert "datasource_count" not in by_id[project_b.id]
    assert inactive.id not in by_id


def test_list_project_resources_returns_generic_discovery_descriptors(db_session, tmp_path) -> None:
    project = Project(
        id=str(uuid.uuid4()),
        name="Project resources",
        status="active",
    )
    db_session.add(project)
    db_session.commit()
    descriptor = ProjectResourceDescriptor(
        kind="acme.resource",
        id="resource-1",
        name="External resource",
        version="v3",
    )
    provider = lambda _db, project_id: (descriptor,) if project_id == project.id else ()
    snapshot = ContributionCompiler(tmp_path / "dlcs").compile(
        built_ins=BuiltinContributionSet(resource_providers=(provider,)),
    )
    set_active_runtime_snapshot(snapshot)
    try:
        resources = api_list_project_resources(project.id, db_session)
    finally:
        set_active_runtime_snapshot(None)

    assert [(resource.kind, resource.id, resource.name) for resource in resources] == [
        ("acme.resource", "resource-1", "External resource"),
    ]
