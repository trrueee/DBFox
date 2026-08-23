"""Product-level contracts exposed through the generated OpenAPI transport."""

from engine.main import app


def test_openapi_exposes_data_only_through_generic_dlc_operations() -> None:
    paths = app.openapi()["paths"]
    retired = (
        "/api/v1/datasources",
        "/api/v1/query/execute",
        "/api/v1/query/validate",
        "/api/v1/query/history",
        "/api/v1/backups",
        "/api/v1/schema/tables",
        "/api/v1/agent/console/execute",
    )
    assert all(path not in paths for path in retired)
    assert "/api/v1/dlcs/{dlc_id}/operations/{operation_name}" in paths


def test_openapi_does_not_publish_retired_core_data_schemas() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert "DataSourceResponse" not in schemas
    assert "SchemaSyncResponse" not in schemas
