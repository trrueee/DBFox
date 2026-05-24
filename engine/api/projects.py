import logging
import uuid
import sys
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.environment import (
    check_environment_health,
    create_local_mysql_environment,
    get_environment_logs,
    start_environment,
    stop_environment,
    destroy_environment,
    rebuild_environment,
)
from engine.errors import DataBoxError
from engine.models import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DataSource,
    DatabaseEnvironment,
    Project,
)
from engine.schemas import ProjectCreateRequest, EnvironmentCreateRequest, DemoStartRequest
from engine.schema_sync import sync_schema
from engine.crypto import encrypt_password

logger = logging.getLogger("databox.api.projects")
router = APIRouter()


def _project_to_dict(project: Project, datasource_count: int = 0) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "status": project.status,
        "datasource_count": datasource_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _environment_to_dict(environment: DatabaseEnvironment) -> dict[str, Any]:
    return {
        "id": environment.id,
        "project_id": environment.project_id,
        "name": environment.name,
        "runtime": environment.runtime,
        "engine_type": environment.engine_type,
        "engine_version": environment.engine_version,
        "image": environment.image,
        "container_name": environment.container_name,
        "host": environment.host,
        "port": environment.port,
        "database_name": environment.database_name,
        "username": environment.username,
        "datasource_id": environment.datasource_id,
        "status": environment.status,
        "last_health_status": environment.last_health_status,
        "last_health_at": environment.last_health_at.isoformat() if environment.last_health_at else None,
        "last_error": environment.last_error,
        "created_at": environment.created_at.isoformat() if environment.created_at else None,
        "updated_at": environment.updated_at.isoformat() if environment.updated_at else None,
    }


def _datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "project_id": ds.project_id or DEFAULT_PROJECT_ID,
        "environment_id": ds.environment_id,
        "name": ds.name,
        "db_type": ds.db_type or "mysql",
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "connection_mode": ds.connection_mode,
        "is_read_only": bool(ds.is_read_only),
        "env": ds.env or "dev",
        "status": ds.status,
        "ssh_enabled": bool(ds.ssh_enabled),
        "ssh_host": ds.ssh_host or "",
        "ssh_port": ds.ssh_port or 22,
        "ssh_username": ds.ssh_username or "",
        "ssh_pkey_path": ds.ssh_pkey_path or "",
        "ssl_enabled": bool(ds.ssl_enabled),
        "ssl_ca_path": ds.ssl_ca_path or "",
        "ssl_cert_path": ds.ssl_cert_path or "",
        "ssl_key_path": ds.ssl_key_path or "",
        "ssl_verify_identity": bool(ds.ssl_verify_identity),
        "last_test_at": ds.last_test_at.isoformat() if ds.last_test_at else None,
        "last_test_status": ds.last_test_status,
        "last_test_error": ds.last_test_error,
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


def _get_or_create_default_project(db: Session) -> Project:
    project = db.query(Project).filter(Project.id == DEFAULT_PROJECT_ID).first()
    if project:
        return project

    project = Project(
        id=DEFAULT_PROJECT_ID,
        name=DEFAULT_PROJECT_NAME,
        description="Auto-created workspace for existing DataBox assets.",
        status="active",
    )
    db.add(project)
    db.flush()
    return project


def _resolve_project_id(db: Session, project_id: str | None) -> str:
    if not project_id:
        return str(_get_or_create_default_project(db).id)
    if project_id == DEFAULT_PROJECT_ID:
        return str(_get_or_create_default_project(db).id)

    project = db.query(Project).filter(Project.id == project_id, Project.status == "active").first()
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})
    return str(project.id)


def _get_environment_or_404(db: Session, environment_id: str) -> DatabaseEnvironment:
    environment = db.query(DatabaseEnvironment).filter(DatabaseEnvironment.id == environment_id).first()
    if not environment:
        raise HTTPException(status_code=404, detail={"code": "ENVIRONMENT_NOT_FOUND", "message": "Environment not found"})
    return environment


@router.get("/projects")
def api_list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _get_or_create_default_project(db)
    db.commit()

    projects = db.query(Project).filter(Project.status == "active").order_by(Project.created_at.asc()).all()
    datasource_counts: dict[str, int] = {}
    for ds in db.query(DataSource).filter(DataSource.project_id.isnot(None)).all():
        datasource_counts[str(ds.project_id)] = datasource_counts.get(str(ds.project_id), 0) + 1

    return [_project_to_dict(project, datasource_counts.get(str(project.id), 0)) for project in projects]


@router.post("/projects")
def api_create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"code": "PROJECT_NAME_REQUIRED", "message": "Project name is required"})

    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=(req.description or "").strip() or None,
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project, 0)


@router.get("/projects/{project_id}/environments")
def api_list_project_environments(project_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _resolve_project_id(db, project_id)
    environments = (
        db.query(DatabaseEnvironment)
        .filter(DatabaseEnvironment.project_id == project_id)
        .order_by(DatabaseEnvironment.created_at.desc())
        .all()
    )
    return [_environment_to_dict(environment) for environment in environments]


@router.get("/environments/docker-status")
def api_get_docker_status() -> dict[str, Any]:
    from engine.demo_mysql import check_docker_available
    return {"available": check_docker_available()}


@router.post("/environments/local-mysql")
def api_create_local_mysql_environment(req: EnvironmentCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        project_id = _resolve_project_id(db, req.project_id)
        environment = create_local_mysql_environment(
            db,
            project_id=project_id,
            name=req.name.strip() or "Local MySQL",
            mysql_version=req.mysql_version,
            seed_demo=req.seed_demo,
        )
        db.commit()
        db.refresh(environment)
        try:
            if environment.datasource_id:
                sync_schema(db, str(environment.datasource_id))
        except Exception as exc:
            logger.warning("Environment datasource schema sync failed: %s", exc)
        return _environment_to_dict(environment)
    except HTTPException:
        db.rollback()
        raise
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create local MySQL environment")
        raise HTTPException(
            status_code=500,
            detail={"code": "ENVIRONMENT_CREATE_FAILED", "message": f"Create local MySQL environment failed: {exc}"},
        )


@router.post("/environments/{environment_id}/start")
def api_start_environment(environment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    try:
        start_environment(environment)
        db.commit()
        db.refresh(environment)
        return _environment_to_dict(environment)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.post("/environments/{environment_id}/stop")
def api_stop_environment(environment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    try:
        stop_environment(environment)
        db.commit()
        db.refresh(environment)
        return _environment_to_dict(environment)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.get("/environments/{environment_id}/health")
def api_check_environment_health(environment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    result = check_environment_health(environment)
    db.commit()
    db.refresh(environment)
    return {"environment": _environment_to_dict(environment), "health": result}


@router.get("/environments/{environment_id}/logs")
def api_get_environment_logs(environment_id: str, tail: int = Query(default=200), db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    try:
        logs = get_environment_logs(environment, tail=max(1, min(tail, 1000)))
        return {"environmentId": environment_id, "logs": logs}
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.delete("/environments/{environment_id}")
def api_destroy_environment(environment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    try:
        destroy_environment(db, environment)
        db.commit()
        return {"ok": True, "message": "Environment successfully destroyed"}
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to destroy environment")
        raise HTTPException(status_code=500, detail={"code": "DESTROY_FAILED", "message": f"Destroy failed: {exc}"})


@router.post("/environments/{environment_id}/rebuild")
def api_rebuild_environment(environment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    environment = _get_environment_or_404(db, environment_id)
    try:
        rebuild_environment(db, environment)
        db.commit()
        db.refresh(environment)
        if environment.datasource_id:
            try:
                sync_schema(db, str(environment.datasource_id))
                db.commit()
            except Exception as sync_exc:
                logger.warning("Failed to sync schema on rebuild: %s", sync_exc)
        return _environment_to_dict(environment)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to rebuild environment")
        raise HTTPException(status_code=500, detail={"code": "REBUILD_FAILED", "message": f"Rebuild failed: {exc}"})


@router.post("/demo/start")
def api_start_demo_mysql(
    req: DemoStartRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from engine.demo_mysql import (
        check_docker_available,
        launch_demo_container,
        wait_for_mysql_port,
        populate_demo_data
    )

    if not check_docker_available():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_NOT_AVAILABLE",
                "message": "未检测到本地 Docker 运行环境，请确保 Docker Desktop 已启动且加入了系统 PATH 环境变量。"
            }
        )

    try:
        launch_demo_container()
    except Exception as e:
        logger.exception("Failed to launch demo container")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_LAUNCH_FAILED",
                "message": f"创建并启动 Docker 容器失败: {str(e)}"
            }
        )

    if not wait_for_mysql_port(timeout=45):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_WAIT_TIMEOUT",
                "message": "等待 Docker MySQL 实例就绪超时，请检查 Docker 中 databox-demo-mysql 容器 of logs。"
            }
        )

    try:
        populate_demo_data()
    except Exception as e:
        logger.exception("Failed to seed demo database")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCKER_SEED_FAILED",
                "message": f"数据库表结构及电商演示数据导入失败: {str(e)}"
            }
        )

    target_project_id = _resolve_project_id(db, req.project_id if req else None)

    # Register datasource in local SQLite
    datasource = db.query(DataSource).filter(
        DataSource.project_id == target_project_id,
        DataSource.host == "127.0.0.1",
        DataSource.port == 3309,
        DataSource.database_name == "databox_demo"
    ).first()

    if not datasource:
        try:
            cipher, nonce = encrypt_password("demo_pass")
            datasource = DataSource(
                id=str(uuid.uuid4()),
                project_id=target_project_id,
                name="本地 Demo 电子商务数据库 (Docker)",
                host="127.0.0.1",
                port=3309,
                database_name="databox_demo",
                username="databox_demo_user",
                password_ciphertext=cipher,
                password_nonce=nonce,
                is_read_only=False,
                env="dev",
                status="active"
            )
            db.add(datasource)
            db.commit()
            db.refresh(datasource)
        except Exception as e:
            db.rollback()
            logger.exception("Failed to register demo datasource in db")
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "DATASOURCE_REGISTER_FAILED",
                    "message": f"自动注册 Demo 数据源失败: {str(e)}"
                }
            )
    elif not datasource.project_id:
        setattr(datasource, "project_id", _resolve_project_id(db, None))
        db.commit()
        db.refresh(datasource)

    # Sync Schema metadata
    try:
        sync_schema(db, str(datasource.id))
    except Exception as e:
        logger.exception("Failed to sync demo database schema")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_FAILED",
                "message": f"自动同步表元数据结构失败: {str(e)}。但数据库连接已保存，您可以手动同步。"
            }
        )

    return _datasource_to_dict(datasource)
