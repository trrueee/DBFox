"""Tests for Semantic Layer v1: DB-driven aliases, metrics, dimensions, and workspace scope."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.main import app
from engine.models import (
    DataSource,
    Project,
    SchemaColumn,
    SchemaTable,
    SemanticAlias,
    WorkspaceTableScope,
)
from engine.semantic import SchemaLinker, SemanticAliasResolver


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with in-memory database override."""
    from engine.main import LOCAL_SECURE_TOKEN

    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"X-Local-Token": LOCAL_SECURE_TOKEN}) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_datasource(db: Session, name: str = "test_ds") -> DataSource:
    ds = DataSource(
        id=str(uuid.uuid4()),
        name=name,
        host="localhost",
        port=3306,
        database_name=f"{name}_db",
        username="test",
        password_ciphertext="x",
        password_nonce="x",
        status="active",
    )
    db.add(ds)
    db.commit()
    return ds


def _make_project(db: Session, name: str = "test_project") -> Project:
    proj = Project(id=str(uuid.uuid4()), name=name, description="test")
    db.add(proj)
    db.commit()
    return proj


def _add_table(db: Session, datasource_id: str, table_name: str, columns: list[tuple[str, str]] | None = None) -> SchemaTable:
    table = SchemaTable(
        id=str(uuid.uuid4()),
        data_source_id=datasource_id,
        table_name=table_name,
        table_schema="public",
    )
    db.add(table)
    db.flush()
    if columns:
        for idx, (col_name, col_type) in enumerate(columns):
            col = SchemaColumn(
                id=str(uuid.uuid4()),
                table_id=table.id,
                column_name=col_name,
                data_type=col_type,
                column_type=col_type,
                ordinal_position=idx,
            )
            db.add(col)
    db.commit()
    db.refresh(table)
    return table


# ---------------------------------------------------------------------------
# Task 1 & 4: DB aliases are resolved + merged with built-ins
# ---------------------------------------------------------------------------

class TestSemanticAliasResolverFromDB:
    def test_from_db_merges_aliases(self, db_session):
        ds = _make_datasource(db_session, "alias_test")
        _add_table(db_session, ds.id, "orders", [("id", "INT"), ("total_amount", "DECIMAL")])
        _add_table(db_session, ds.id, "users", [("id", "INT"), ("username", "VARCHAR")])

        db_alias = SemanticAlias(
            id=str(uuid.uuid4()),
            data_source_id=ds.id,
            alias="GMV",
            target_type="column",
            target="orders.total_amount",
        )
        db_session.add(db_alias)
        db_session.commit()

        resolver = SemanticAliasResolver.from_db(db_session, ds.id)
        assert "GMV" in resolver.aliases
        assert resolver.aliases["GMV"] == "orders.total_amount"
        # built-in aliases still present
        assert "销售额" in resolver.aliases

    def test_db_alias_takes_priority_over_builtin(self, db_session):
        ds = _make_datasource(db_session, "priority_test")
        _add_table(db_session, ds.id, "orders", [("id", "INT"), ("total_amount", "DECIMAL")])

        # A DB alias that overrides a built-in
        db_alias = SemanticAlias(
            id=str(uuid.uuid4()),
            data_source_id=ds.id,
            alias="GMV",
            target_type="column",
            target="orders.id",  # different from built-in "orders.total_amount"
        )
        db_session.add(db_alias)
        db_session.commit()

        resolver = SemanticAliasResolver.from_db(db_session, ds.id)
        assert resolver.aliases["GMV"] == "orders.id"

    def test_resolve_marks_source(self, db_session):
        ds = _make_datasource(db_session, "source_test")
        _add_table(db_session, ds.id, "orders", [("id", "INT"), ("total_amount", "DECIMAL")])

        db_alias = SemanticAlias(
            id=str(uuid.uuid4()),
            data_source_id=ds.id,
            alias="测试指标",
            target_type="column",
            target="orders.total_amount",
        )
        db_session.add(db_alias)
        db_session.commit()

        resolver = SemanticAliasResolver.from_db(db_session, ds.id)
        matches = resolver.resolve("统计 测试指标")
        db_matches = [m for m in matches if m.alias == "测试指标"]
        assert len(db_matches) == 1
        assert db_matches[0].source == "db"

    def test_schema_linker_uses_db_alias_resolver(self, db_session):
        ds = _make_datasource(db_session, "linker_alias_test")
        _add_table(db_session, ds.id, "products", [("id", "INT"), ("name", "VARCHAR"), ("price", "DECIMAL")])
        _add_table(db_session, ds.id, "admin_logs", [("id", "INT"), ("action", "VARCHAR")])

        db_alias = SemanticAlias(
            id=str(uuid.uuid4()),
            data_source_id=ds.id,
            alias="商品价格",
            target_type="column",
            target="products.price",
        )
        db_session.add(db_alias)
        db_session.commit()

        result = SchemaLinker(db_session).link(datasource_id=ds.id, question="查询 商品价格")
        assert "products" in result.selected_table_names()
        assert "products.price" in result.selected_column_names()

        aliases_used = result.semantic_aliases_used
        assert any(a["alias"] == "商品价格" for a in aliases_used)
        assert any(a["source"] == "db" for a in aliases_used)


# ---------------------------------------------------------------------------
# Task 5: WorkspaceTableScope
# ---------------------------------------------------------------------------

class TestWorkspaceTableScope:
    def test_scope_limits_candidate_tables(self, db_session):
        ds = _make_datasource(db_session, "scope_test")
        proj = _make_project(db_session, "scope_project")

        orders = _add_table(db_session, ds.id, "orders", [("id", "INT")])
        _add_table(db_session, ds.id, "admin_logs", [("id", "INT")])
        _add_table(db_session, ds.id, "system_settings", [("id", "INT")])

        scope = WorkspaceTableScope(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            data_source_id=ds.id,
            table_id=orders.id,
            enabled=True,
        )
        db_session.add(scope)
        db_session.commit()

        result = SchemaLinker(db_session).link(
            datasource_id=ds.id,
            question="统计所有数据",
            project_id=proj.id,
        )

        assert result.workspace_scope_applied is True
        assert result.workspace_scope_table_count == 1
        table_names = result.selected_table_names()
        assert "orders" in table_names
        assert "admin_logs" not in table_names
        assert "system_settings" not in table_names

    def test_no_scope_keeps_all_tables(self, db_session):
        ds = _make_datasource(db_session, "noscope_test")
        _add_table(db_session, ds.id, "orders", [("id", "INT")])
        _add_table(db_session, ds.id, "admin_logs", [("id", "INT")])

        result = SchemaLinker(db_session).link(datasource_id=ds.id, question="统计")
        assert result.workspace_scope_applied is False
        assert result.workspace_scope_table_count == 0
        assert "orders" in result.selected_table_names()
        assert "admin_logs" in result.selected_table_names()

    def test_scope_present_in_response_metadata(self, db_session):
        ds = _make_datasource(db_session, "meta_test")
        proj = _make_project(db_session, "meta_project")
        table = _add_table(db_session, ds.id, "orders", [("id", "INT")])

        scope = WorkspaceTableScope(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            data_source_id=ds.id,
            table_id=table.id,
            enabled=True,
        )
        db_session.add(scope)
        db_session.commit()

        result = SchemaLinker(db_session).link(
            datasource_id=ds.id,
            question="统计",
            project_id=proj.id,
        )
        meta = result.response_metadata("fake context")
        assert meta["workspaceScopeApplied"] is True
        assert meta["workspaceScopeTableCount"] == 1

    def test_explicit_workspace_table_ids_take_priority(self, db_session):
        """Explicit workspace_table_ids override project_id scope."""
        ds = _make_datasource(db_session, "override_test")
        proj = _make_project(db_session, "override_project")
        orders = _add_table(db_session, ds.id, "orders", [("id", "INT")])
        products = _add_table(db_session, ds.id, "products", [("id", "INT")])

        # project_id scope gives orders only
        scope = WorkspaceTableScope(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            data_source_id=ds.id,
            table_id=orders.id,
            enabled=True,
        )
        db_session.add(scope)
        db_session.commit()

        # But explicit workspace_table_ids should take priority
        result = SchemaLinker(db_session).link(
            datasource_id=ds.id,
            question="products",
            workspace_table_ids=[products.id],
            project_id=proj.id,
        )

        assert "products" in result.selected_table_names()


# ---------------------------------------------------------------------------
# Task 6: Semantic metric & dimension in QueryPlan
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Task 3: Semantic API endpoints
# ---------------------------------------------------------------------------

class TestSemanticAPI:
    def test_table_scope_save_and_read(self, client, db_session, test_datasource):
        from engine.models import Project
        proj = Project(id=str(uuid.uuid4()), name="scope_api_test", description="")
        db_session.add(proj)
        db_session.commit()

        from engine.semantic.schema_linker import SchemaLinker
        ds_id = test_datasource.id
        linker = SchemaLinker(db_session)
        all_tables = (
            db_session.query(SchemaTable)
            .filter(SchemaTable.data_source_id == ds_id)
            .all()
        )
        if not all_tables:
            pytest.skip("No synced tables in demo datasource")

        enabled_ids = [str(t.id) for t in all_tables[:2]]

        resp = client.post("/api/v1/semantic/table-scope", json={
            "project_id": proj.id,
            "datasource_id": ds_id,
            "enabled_table_ids": enabled_ids,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        get_resp = client.get(f"/api/v1/semantic/table-scope?project_id={proj.id}&datasource_id={ds_id}")
        assert get_resp.status_code == 200
        scopes = get_resp.json()
        assert len(scopes) == len(enabled_ids)

    def test_table_scope_rejects_invalid_table(self, client, db_session, test_datasource):
        from engine.models import Project
        proj = Project(id=str(uuid.uuid4()), name="invalid_test", description="")
        db_session.add(proj)
        db_session.commit()

        resp = client.post("/api/v1/semantic/table-scope", json={
            "project_id": proj.id,
            "datasource_id": test_datasource.id,
            "enabled_table_ids": ["nonexistent-table-id"],
        })
        assert resp.status_code == 400

    def test_aliases_require_valid_datasource(self, client, db_session):
        resp = client.post("/api/v1/semantic/aliases", json={
            "data_source_id": "nonexistent-ds",
            "alias": "test",
            "target_type": "table",
            "target": "t",
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Agent integration: schema context + query plan
# ---------------------------------------------------------------------------


class TestAgentSemanticIntegration:
    def test_agent_build_schema_context_works_with_semantic_layer(self, db_session):
        """Agent's build_schema_context path still works after semantic layer changes."""
        ds = _make_datasource(db_session, "agent_context_test")
        _add_table(db_session, ds.id, "orders", [("id", "INT"), ("total_amount", "DECIMAL")])
        _add_table(db_session, ds.id, "users", [("id", "INT"), ("username", "VARCHAR")])

        # Add a DB alias
        db_session.add(SemanticAlias(
            id=str(uuid.uuid4()), data_source_id=ds.id,
            alias="GMV", target_type="column", target="orders.total_amount",
        ))
        db_session.commit()

        # Simulate what build_schema_context_tool does
        from engine.semantic import SchemaContextBuilder
        linker = SchemaLinker(db_session)
        result = linker.link(datasource_id=ds.id, question="统计 GMV")
        context = SchemaContextBuilder(db_session).build(result)
        metadata = result.response_metadata(context)

        assert "semanticAliasesUsed" in metadata
        assert any(a["alias"] == "GMV" for a in metadata["semanticAliasesUsed"])
        assert "orders" in str(context)



