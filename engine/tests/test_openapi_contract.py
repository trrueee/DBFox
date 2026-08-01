"""Product-level contracts exposed through the generated OpenAPI transport."""

from engine.main import app


def test_openapi_does_not_expose_raw_rows_query_execution() -> None:
    assert "/api/v1/query/execute" not in app.openapi()["paths"]


def test_openapi_keeps_schema_sync_response_closed() -> None:
    schema = app.openapi()["components"]["schemas"]["SchemaSyncResponse"]

    assert schema["additionalProperties"] is False
    assert {
        "tablesDropped",
        "columnsCreated",
        "columnsUpdated",
        "columnsRemoved",
    } <= set(schema["properties"])


def test_openapi_marks_datasource_connection_fields_nullable() -> None:
    properties = app.openapi()["components"]["schemas"]["DataSourceResponse"]["properties"]

    for name in ("host", "username"):
        assert {variant.get("type") for variant in properties[name]["anyOf"]} == {
            "string",
            "null",
        }
