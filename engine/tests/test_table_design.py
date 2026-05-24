from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.table_design import generate_create_table_ddl


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_generate_create_table_ddl_basic() -> None:
    result = generate_create_table_ddl({
        "table_name": "orders",
        "table_comment": "订单表",
        "columns": [
            {
                "name": "id",
                "type": "BIGINT",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "comment": "主键",
            },
            {
                "name": "status",
                "type": "VARCHAR(32)",
                "nullable": False,
                "default_value": "pending",
                "comment": "状态",
            },
            {
                "name": "amount",
                "type": "DECIMAL(10,2)",
                "nullable": False,
                "default_value": "0",
            },
        ],
        "indexes": [
            {"name": "idx_orders_status", "columns": ["status"], "unique": False},
        ],
    })

    ddl = result["ddl"]
    assert "CREATE TABLE `orders`" in ddl
    assert "`id` BIGINT NOT NULL AUTO_INCREMENT" in ddl
    assert "`status` VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '状态'" in ddl
    assert "PRIMARY KEY (`id`)" in ddl
    assert "KEY `idx_orders_status` (`status`)" in ddl
    assert "COMMENT='订单表';" in ddl


def test_generate_create_table_ddl_warns_without_primary_key() -> None:
    result = generate_create_table_ddl({
        "table_name": "logs",
        "columns": [
            {"name": "message", "type": "VARCHAR(255)", "nullable": False},
        ],
    })

    assert result["warnings"]
    assert "主键" in result["warnings"][0]


def test_generate_create_table_ddl_rejects_unsafe_identifier() -> None:
    try:
        generate_create_table_ddl({
            "table_name": "users;drop",
            "columns": [{"name": "id", "type": "INT", "primary_key": True}],
        })
    except Exception as exc:
        assert "TABLE_DESIGN_INVALID" in getattr(exc, "code", "")
    else:
        raise AssertionError("Unsafe table name should be rejected")


def test_generate_create_table_ddl_rejects_unsafe_type() -> None:
    try:
        generate_create_table_ddl({
            "table_name": "users",
            "columns": [{"name": "id", "type": "INT); DROP TABLE users; --"}],
        })
    except Exception as exc:
        assert "TABLE_DESIGN_INVALID" in getattr(exc, "code", "")
    else:
        raise AssertionError("Unsafe column type should be rejected")


def test_generate_create_table_ddl_rejects_missing_index_column() -> None:
    try:
        generate_create_table_ddl({
            "table_name": "users",
            "columns": [{"name": "id", "type": "INT", "primary_key": True}],
            "indexes": [{"columns": ["missing_col"]}],
        })
    except Exception as exc:
        assert "TABLE_DESIGN_INVALID" in getattr(exc, "code", "")
    else:
        raise AssertionError("Index referencing a missing column should be rejected")


def test_create_table_ddl_endpoint(db_session) -> None:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/schema/design/create-table-ddl",
                headers=_headers(),
                json={
                    "table_name": "customers",
                    "table_comment": "客户表",
                    "columns": [
                        {
                            "name": "id",
                            "type": "BIGINT",
                            "nullable": False,
                            "primary_key": True,
                            "auto_increment": True,
                        },
                        {"name": "email", "type": "VARCHAR(255)", "nullable": False},
                    ],
                    "indexes": [
                        {"columns": ["email"], "unique": True},
                    ],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["tableName"] == "customers"
    assert "UNIQUE KEY `uk_customers_email` (`email`)" in data["ddl"]


def test_create_table_ddl_endpoint_rejects_bad_design(db_session) -> None:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/schema/design/create-table-ddl",
                headers=_headers(),
                json={
                    "table_name": "bad name",
                    "columns": [{"name": "id", "type": "INT"}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "TABLE_DESIGN_INVALID"


def test_execute_table_design_ddl_success(db_session, demo_datasource) -> None:
    from engine.table_design import execute_table_design_ddl
    from engine.models import QueryHistory
    import uuid

    # Execute a clean CREATE TABLE DDL
    tbl_name = f"test_new_table_{uuid.uuid4().hex[:8]}"
    ddl = f"CREATE TABLE `{tbl_name}` (`id` INT PRIMARY KEY, `val` VARCHAR(50));"
    res = execute_table_design_ddl(db_session, demo_datasource.id, ddl)

    assert res["success"] is True
    assert "成功" in res["message"]

    # Verify query history logged
    history = db_session.query(QueryHistory).filter(
        QueryHistory.data_source_id == demo_datasource.id,
        QueryHistory.submitted_sql == ddl
    ).first()
    assert history is not None
    assert history.question == "Execute Designed DDL"
    assert history.submitted_sql == ddl
    assert history.execution_status == "success"


def test_execute_table_design_ddl_readonly_error(db_session, demo_datasource) -> None:
    from engine.table_design import execute_table_design_ddl, TableDesignError
    import uuid

    # Mark data source read-only
    demo_datasource.is_read_only = True
    db_session.commit()

    tbl_name = f"test_new_table2_{uuid.uuid4().hex[:8]}"
    ddl = f"CREATE TABLE `{tbl_name}` (`id` INT PRIMARY KEY);"
    try:
        execute_table_design_ddl(db_session, demo_datasource.id, ddl)
    except TableDesignError as exc:
        assert "只读模式" in str(exc)
    else:
        raise AssertionError("Read-only data source should reject DDL execution")


def test_execute_table_design_ddl_non_create_error(db_session, demo_datasource) -> None:
    from engine.table_design import execute_table_design_ddl, TableDesignError
    import uuid

    tbl_name = f"test_new_table3_{uuid.uuid4().hex[:8]}"
    ddl = f"DROP TABLE `{tbl_name}`;"
    try:
        execute_table_design_ddl(db_session, demo_datasource.id, ddl)
    except TableDesignError as exc:
        assert "仅支持执行 CREATE TABLE" in str(exc)
    else:
        raise AssertionError("Non-CREATE TABLE DDL should be rejected")


def test_execute_table_design_ddl_endpoint(db_session, demo_datasource) -> None:
    import uuid
    def override_get_db():
        yield db_session

    tbl_name = f"api_test_table_{uuid.uuid4().hex[:8]}"
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": f"CREATE TABLE `{tbl_name}` (`id` INT PRIMARY KEY);"
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_table_design_draft_api_endpoints(db_session) -> None:
    from engine.models import Project, TableDesignDraft
    # Ensure a project exists
    proj = db_session.query(Project).first()
    if not proj:
        proj = Project(id="test-proj", name="Test Project")
        db_session.add(proj)
        db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # 1. Save new draft
            resp = client.post(
                "/api/v1/schema/design/drafts/save",
                headers=_headers(),
                json={
                    "project_id": proj.id,
                    "table_name": "draft_table",
                    "table_comment": "Draft Comment",
                    "columns": [
                        {"name": "id", "type": "INT", "nullable": False, "primary_key": True, "auto_increment": True}
                    ],
                    "indexes": []
                }
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["table_name"] == "draft_table"
            draft_id = data["id"]

            # 2. Get single draft
            resp = client.get(
                f"/api/v1/schema/design/drafts/{draft_id}",
                headers=_headers()
            )
            assert resp.status_code == 200
            assert resp.json()["table_comment"] == "Draft Comment"

            # 3. List drafts
            resp = client.get(
                f"/api/v1/schema/design/drafts?project_id={proj.id}",
                headers=_headers()
            )
            assert resp.status_code == 200
            drafts = resp.json()
            assert len(drafts) > 0
            assert any(d["id"] == draft_id for d in drafts)

            # 4. Update existing draft
            resp = client.post(
                "/api/v1/schema/design/drafts/save",
                headers=_headers(),
                json={
                    "project_id": proj.id,
                    "draft_id": draft_id,
                    "table_name": "draft_table_updated",
                    "table_comment": "Updated Comment",
                    "columns": [
                        {"name": "id", "type": "INT", "nullable": False, "primary_key": True, "auto_increment": True},
                        {"name": "name", "type": "VARCHAR(100)", "nullable": True}
                    ],
                    "indexes": []
                }
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["table_name"] == "draft_table_updated"
            assert data["table_comment"] == "Updated Comment"
            assert len(data["columns"]) == 2

            # 5. Delete draft
            resp = client.delete(
                f"/api/v1/schema/design/drafts/{draft_id}",
                headers=_headers()
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            # 6. Verify deleted
            resp = client.get(
                f"/api/v1/schema/design/drafts/{draft_id}",
                headers=_headers()
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_generate_table_design_ai():
    with TestClient(app) as client:
        # Test typical user template matching (offline mode)
        resp = client.post(
            "/api/v1/schema/design/ai-generate",
            headers=_headers(),
            json={"prompt": "我需要一张用户表，加几个常用字段", "api_key": None}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["table_name"] == "users"
        assert "columns" in data
        assert any(c["name"] == "username" for c in data["columns"])

        # Test dynamic fallback matching (offline mode)
        resp2 = client.post(
            "/api/v1/schema/design/ai-generate",
            headers=_headers(),
            json={"prompt": "帮我设计一张名为 article 的文章表，需要有标题 title 和文章状态 status 以及发布时间 created_at 字段", "api_key": None}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "columns" in data2
        # Should dynamically match columns based on keyword matching
        assert any(c["name"] == "name" for c in data2["columns"])  # 'title' maps to name
        assert any(c["name"] == "status" for c in data2["columns"])  # status
        assert any(c["name"] == "created_at" for c in data2["columns"])  # created_at




