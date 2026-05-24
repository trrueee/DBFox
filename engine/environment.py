from __future__ import annotations

import socket
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any

import pymysql
from sqlalchemy.orm import Session

from engine.crypto import decrypt_password, encrypt_password
from engine.demo_mysql import check_docker_available, populate_demo_data, wait_for_mysql_port
from engine.errors import DataBoxError
from engine.models import DatabaseEnvironment, DataSource


class EnvironmentError(DataBoxError):
    def __init__(self, message: str, code: str = "ENVIRONMENT_FAILED") -> None:
        super().__init__(message, code=code)


def _run_docker(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise EnvironmentError(f"Docker command failed: {detail}") from exc
    except Exception as exc:
        raise EnvironmentError(f"Docker command failed: {exc}") from exc


def ensure_docker_available() -> None:
    if not check_docker_available():
        raise EnvironmentError(
            "Docker is not available. Please start Docker Desktop and make sure docker is in PATH.",
            code="DOCKER_NOT_AVAILABLE",
        )


def allocate_local_port(start_port: int = 3310, max_attempts: int = 100) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise EnvironmentError("No available local port found for MySQL environment.", code="PORT_UNAVAILABLE")


def get_container_status(container_name: str) -> str:
    try:
        result = _run_docker(
            ["ps", "-a", "--filter", f"name={container_name}", "--format", "{{.State}}"],
            timeout=10,
        )
        state = result.stdout.strip()
        if not state:
            return "missing"
        return "running" if "running" in state else "stopped"
    except EnvironmentError:
        return "unknown"


def create_local_mysql_environment(
    db: Session,
    project_id: str,
    name: str,
    mysql_version: str = "8.0",
    seed_demo: bool = True,
) -> DatabaseEnvironment:
    ensure_docker_available()

    env_id = str(uuid.uuid4())
    datasource_id = str(uuid.uuid4())
    suffix = env_id.split("-")[0]
    port = allocate_local_port()
    image = f"mysql:{mysql_version}"
    container_name = f"databox-mysql-{suffix}"
    database_name = f"databox_{suffix}"
    username = "databox_user"
    password = f"databox_{suffix}_pass"
    root_password = f"databox_{suffix}_root"

    _run_docker(
        [
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{port}:3306",
            "-e",
            f"MYSQL_ROOT_PASSWORD={root_password}",
            "-e",
            f"MYSQL_DATABASE={database_name}",
            "-e",
            f"MYSQL_USER={username}",
            "-e",
            f"MYSQL_PASSWORD={password}",
            image,
        ],
        timeout=60,
    )

    if not wait_for_mysql_port(timeout=60, port=port):
        raise EnvironmentError("Timed out waiting for MySQL environment to become ready.", code="ENV_WAIT_TIMEOUT")

    if seed_demo:
        populate_demo_data(port=port, root_password=root_password, database_name=database_name)

    cipher, nonce = encrypt_password(password)
    datasource = DataSource(
        id=datasource_id,
        project_id=project_id,
        environment_id=env_id,
        name=f"{name} DataSource",
        host="127.0.0.1",
        port=port,
        database_name=database_name,
        username=username,
        password_ciphertext=cipher,
        password_nonce=nonce,
        is_read_only=False,
        env="dev",
        status="active",
    )
    environment = DatabaseEnvironment(
        id=env_id,
        project_id=project_id,
        name=name,
        runtime="docker",
        engine_type="mysql",
        engine_version=mysql_version,
        image=image,
        container_name=container_name,
        host="127.0.0.1",
        port=port,
        database_name=database_name,
        username=username,
        password_ciphertext=cipher,
        password_nonce=nonce,
        datasource_id=datasource_id,
        status="running",
        last_health_status="healthy",
        last_health_at=datetime.now(UTC),
    )
    db.add(environment)
    db.add(datasource)
    db.flush()
    return environment


def start_environment(environment: DatabaseEnvironment) -> None:
    ensure_docker_available()
    status = get_container_status(str(environment.container_name))
    if status == "missing":
        raise EnvironmentError("Docker container is missing.", code="ENV_CONTAINER_MISSING")
    if status != "running":
        _run_docker(["start", str(environment.container_name)], timeout=30)
    setattr(environment, "status", "running")
    setattr(environment, "last_error", None)


def stop_environment(environment: DatabaseEnvironment) -> None:
    ensure_docker_available()
    status = get_container_status(str(environment.container_name))
    if status == "running":
        _run_docker(["stop", str(environment.container_name)], timeout=30)
    setattr(environment, "status", "stopped")


def get_environment_logs(environment: DatabaseEnvironment, tail: int = 200) -> str:
    ensure_docker_available()
    result = _run_docker(["logs", "--tail", str(tail), str(environment.container_name)], timeout=20)
    return (result.stdout or "") + (result.stderr or "")


def check_environment_health(environment: DatabaseEnvironment) -> dict[str, Any]:
    container_status = get_container_status(str(environment.container_name))
    tcp_ok = False
    mysql_ok = False
    error_message = None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect((str(environment.host), int(environment.port)))
            tcp_ok = True
    except Exception as exc:
        error_message = str(exc)

    if tcp_ok:
        try:
            password = decrypt_password(str(environment.password_ciphertext), str(environment.password_nonce))
            conn = pymysql.connect(
                host=str(environment.host),
                port=int(environment.port),
                user=str(environment.username),
                password=password,
                database=str(environment.database_name),
                connect_timeout=3,
                read_timeout=3,
                write_timeout=3,
            )
            conn.close()
            mysql_ok = True
        except Exception as exc:
            error_message = str(exc)

    health_status = "healthy" if container_status == "running" and tcp_ok and mysql_ok else "unhealthy"
    setattr(environment, "status", "running" if container_status == "running" else container_status)
    setattr(environment, "last_health_status", health_status)
    setattr(environment, "last_health_at", datetime.now(UTC))
    setattr(environment, "last_error", None if health_status == "healthy" else error_message)

    return {
        "status": health_status,
        "containerStatus": container_status,
        "tcpOk": tcp_ok,
        "mysqlOk": mysql_ok,
        "error": error_message,
    }


def destroy_environment(db: Session, environment: DatabaseEnvironment) -> None:
    ensure_docker_available()
    try:
        _run_docker(["rm", "-f", str(environment.container_name)], timeout=30)
    except Exception:
        # Ignore container removal error if it is already deleted manualy
        pass

    # Delete the associated DataSource
    if environment.datasource_id:
        ds = db.query(DataSource).filter(DataSource.id == environment.datasource_id).first()
        if ds:
            db.delete(ds)

    db.delete(environment)
    db.flush()


def rebuild_environment(db: Session, environment: DatabaseEnvironment) -> DatabaseEnvironment:
    ensure_docker_available()

    # 1. Stop and remove the old Docker container
    try:
        _run_docker(["rm", "-f", str(environment.container_name)], timeout=30)
    except Exception:
        pass

    # 2. Re-run docker run with same port, image, database_name, and credentials
    password = decrypt_password(str(environment.password_ciphertext), str(environment.password_nonce))
    suffix = str(environment.id).split("-")[0]
    root_password = f"databox_{suffix}_root"

    _run_docker(
        [
            "run",
            "-d",
            "--name",
            str(environment.container_name),
            "-p",
            f"{environment.port}:3306",
            "-e",
            f"MYSQL_ROOT_PASSWORD={root_password}",
            "-e",
            f"MYSQL_DATABASE={environment.database_name}",
            "-e",
            f"MYSQL_USER={environment.username}",
            "-e",
            f"MYSQL_PASSWORD={password}",
            str(environment.image),
        ],
        timeout=60,
    )

    if not wait_for_mysql_port(timeout=60, port=int(environment.port)):
        raise EnvironmentError("Timed out waiting for MySQL environment to become ready.", code="ENV_WAIT_TIMEOUT")

    # 3. Seed demo data
    populate_demo_data(port=int(environment.port), root_password=root_password, database_name=str(environment.database_name))

    # 4. Update environment status
    setattr(environment, "status", "running")
    setattr(environment, "last_health_status", "healthy")
    setattr(environment, "last_health_at", datetime.now(UTC))
    setattr(environment, "last_error", None)
    db.flush()

    return environment

