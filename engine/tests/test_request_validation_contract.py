from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.schemas.backup import BackupCreateRequest
from engine.schemas.datasource import DataSourceCreateRequest, DataSourceTestRequest, DataSourceUpdateRequest
from engine.api.agent import ConsoleExecuteRequest
from engine.schemas.table_design import (
    TableDesignAIRequest,
    TableDesignDDLRequest,
    TableDesignDraftSaveRequest,
    TableDesignExecuteRequest,
)
from engine.api.datasources import ColumnMetadataUpdateRequest, TableMetadataUpdateRequest


def _datasource_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "local",
        "db_type": "sqlite",
        "host": None,
        "port": 0,
        "database_name": "/tmp/local.db",
        "username": None,
        "connection_mode": "direct",
        "env": "dev",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("db_type", "oracle"),
        ("env", "production"),
        ("connection_mode", "tunnel"),
        ("port", -1),
        ("port", 70_000),
        ("ssh_port", 0),
    ],
)
def test_datasource_create_rejects_invalid_core_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        DataSourceCreateRequest(**_datasource_payload(**{field: value}))


def test_datasource_update_uses_same_core_validation() -> None:
    with pytest.raises(ValidationError):
        DataSourceUpdateRequest(**_datasource_payload(db_type="sqlserver"))


def _datasource_request_payload(
    request_cls: type[DataSourceCreateRequest | DataSourceUpdateRequest | DataSourceTestRequest],
) -> dict[str, object]:
    payload = _datasource_payload()
    if request_cls is DataSourceTestRequest:
        return {
            key: payload[key]
            for key in ("db_type", "host", "port", "database_name", "username")
        }
    return payload


@pytest.mark.parametrize(
    "request_cls",
    [DataSourceCreateRequest, DataSourceUpdateRequest, DataSourceTestRequest],
)
@pytest.mark.parametrize("plaintext_field", ["password", "ssh_password", "ssh_pkey_passphrase"])
def test_datasource_request_rejects_plaintext_secret_fields(
    request_cls: type[DataSourceCreateRequest | DataSourceUpdateRequest | DataSourceTestRequest],
    plaintext_field: str,
) -> None:
    payload = _datasource_request_payload(request_cls)
    payload[plaintext_field] = " plaintext secret "

    with pytest.raises(ValidationError) as exc_info:
        request_cls(**payload)

    assert any(error["loc"][-1] == plaintext_field for error in exc_info.value.errors())


@pytest.mark.parametrize(
    "payload",
    [
        {"datasourceId": "", "sql": "SELECT 1"},
        {"datasourceId": "ds-1", "sql": ""},
        {"datasourceId": "ds-1", "sql": "   "},
        {"datasourceId": "d" * 129, "sql": "SELECT 1"},
        {"datasourceId": "ds-1", "sql": "SELECT 1", "sessionId": "x" * 129},
        {"datasourceId": "ds-1", "sql": "SELECT 1", "executionId": "x" * 129},
    ],
)
def test_console_execute_request_rejects_invalid_core_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsoleExecuteRequest(**payload)


def _table_design_column(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "user_id",
        "type": "BIGINT",
        "nullable": False,
    }
    payload.update(overrides)
    return payload


def _table_design_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "table_name": "users",
        "columns": [_table_design_column()],
        "indexes": [{"name": "idx_user_id", "columns": ["user_id"], "unique": False}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("table_name", ""),
        ("table_name", "users; DROP TABLE users"),
        ("table_name", "1users"),
        ("columns", []),
        ("columns", [_table_design_column(name="bad column")]),
        ("indexes", [{"name": "idx;drop", "columns": ["user_id"], "unique": False}]),
        ("indexes", [{"name": "idx_user_id", "columns": ["bad column"], "unique": False}]),
    ],
)
def test_table_design_ddl_request_rejects_invalid_identifiers_and_empty_columns(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        TableDesignDDLRequest(**_table_design_payload(**{field: value}))


@pytest.mark.parametrize(
    "payload",
    [
        {"datasource_id": "", "ddl": "CREATE TABLE users (id BIGINT)"},
        {"datasource_id": "ds-1", "ddl": ""},
        {"datasource_id": "ds-1", "ddl": " " * 3},
        {"datasource_id": "d" * 129, "ddl": "CREATE TABLE users (id BIGINT)"},
        {"datasource_id": "ds-1", "ddl": "x" * 200_001},
    ],
)
def test_table_design_execute_request_rejects_invalid_core_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TableDesignExecuteRequest(**payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", ""),
        ("project_id", "p" * 129),
        ("table_name", "bad table"),
        ("columns", []),
    ],
)
def test_table_design_draft_request_reuses_safe_table_constraints(field: str, value: object) -> None:
    payload = {
        "project_id": "proj-1",
        **_table_design_payload(),
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        TableDesignDraftSaveRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": ""},
        {"prompt": " " * 3},
        {"prompt": "x" * 20_001},
        {"prompt": "create users", "api_base": "x" * 2049},
        {"prompt": "create users", "model_name": "m" * 129},
    ],
)
def test_table_design_ai_request_rejects_invalid_core_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TableDesignAIRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"datasource_id": ""},
        {"datasource_id": "   "},
        {"datasource_id": "d" * 129},
        {"datasource_id": "ds-1", "label": "l" * 129},
    ],
)
def test_backup_create_request_rejects_invalid_core_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BackupCreateRequest(**payload)


def test_backup_create_request_rejects_removed_fallback_contract() -> None:
    with pytest.raises(ValidationError):
        BackupCreateRequest(datasource_id="ds-1", allow_fallback=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"ai_description": "x" * 2001},
        {"semantic_tags": "x" * 1001},
        {"business_terms": "x" * 1001},
        {"subject_area": "x" * 129},
        {"ai_confidence": -0.01},
        {"ai_confidence": 1.01},
    ],
)
def test_table_metadata_update_request_rejects_invalid_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TableMetadataUpdateRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"ai_description": "x" * 2001},
        {"semantic_tags": "x" * 1001},
        {"business_terms": "x" * 1001},
        {"ai_confidence": -0.01},
        {"ai_confidence": 1.01},
    ],
)
def test_column_metadata_update_request_rejects_invalid_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ColumnMetadataUpdateRequest(**payload)
