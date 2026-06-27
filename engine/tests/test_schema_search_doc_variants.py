import json

from engine.environment.schema_catalog_sync import ensure_catalog, rebuild_search_docs
from engine.models import SchemaColumn, SchemaSearchDoc, SchemaTable


def _seed_ai_metadata(db_session, datasource_id: str) -> None:
    users = (
        db_session.query(SchemaTable)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaTable.table_name == "users",
        )
        .one()
    )
    users.ai_description = "Customer account records for login and signup."
    users.semantic_tags = json.dumps(["customer", "account"], ensure_ascii=False)
    users.business_terms = json.dumps(["member", "registration"], ensure_ascii=False)
    users.aliases = json.dumps(["customer_account"], ensure_ascii=False)
    users.table_role = "dim"
    users.grain = "one row per customer account"
    users.subject_area = "user"
    users.ai_confidence = 0.91

    email = (
        db_session.query(SchemaColumn)
        .filter(
            SchemaColumn.table_id == users.id,
            SchemaColumn.column_name == "email",
        )
        .one()
    )
    email.ai_description = "Email address used as the customer login identifier."
    email.semantic_tags = json.dumps(["email", "login"], ensure_ascii=False)
    email.business_terms = json.dumps(["contact email"], ensure_ascii=False)
    email.aliases = json.dumps(["login_email"], ensure_ascii=False)
    email.column_role = "identifier"
    email.metric_type = "dimension"
    email.ai_confidence = 0.88
    db_session.commit()


def _doc(db_session, datasource_id: str, entity_type: str, name: str) -> SchemaSearchDoc:
    query = db_session.query(SchemaSearchDoc).filter(
        SchemaSearchDoc.datasource_id == datasource_id,
        SchemaSearchDoc.entity_type == entity_type,
    )
    if entity_type == "table":
        query = query.filter(SchemaSearchDoc.table_name == name)
    else:
        table_name, column_name = name.split(".", 1)
        query = query.filter(
            SchemaSearchDoc.table_name == table_name,
            SchemaSearchDoc.column_name == column_name,
        )
    return query.one()


def test_rebuild_search_docs_can_materialize_base_without_ai_metadata(db_session, test_datasource) -> None:
    ensure_catalog(db_session, test_datasource.id, ai_enrich=False)
    _seed_ai_metadata(db_session, test_datasource.id)

    rebuild_search_docs(db_session, test_datasource.id, include_ai_metadata=False)

    table_doc = _doc(db_session, test_datasource.id, "table", "users")
    column_doc = _doc(db_session, test_datasource.id, "column", "users.email")

    assert table_doc.ai_description is None
    assert table_doc.semantic_tags is None
    assert table_doc.business_terms is None
    assert table_doc.aliases is None
    assert table_doc.table_role is None
    assert table_doc.grain is None
    assert table_doc.subject_area is None
    assert table_doc.ai_confidence is None
    assert "Customer account records" not in table_doc.search_text
    assert "customer_account" not in table_doc.search_text
    assert "users" in table_doc.search_text
    assert "email" in table_doc.search_text

    assert column_doc.ai_description is None
    assert column_doc.semantic_tags is None
    assert column_doc.business_terms is None
    assert column_doc.aliases is None
    assert column_doc.column_role is None
    assert column_doc.metric_type is None
    assert "customer login identifier" not in column_doc.search_text
    assert "email" in column_doc.search_text


def test_rebuild_search_docs_can_materialize_ai_enriched_metadata(db_session, test_datasource) -> None:
    ensure_catalog(db_session, test_datasource.id, ai_enrich=False)
    _seed_ai_metadata(db_session, test_datasource.id)

    rebuild_search_docs(db_session, test_datasource.id, include_ai_metadata=True)

    table_doc = _doc(db_session, test_datasource.id, "table", "users")
    column_doc = _doc(db_session, test_datasource.id, "column", "users.email")

    assert table_doc.ai_description == "Customer account records for login and signup."
    assert json.loads(table_doc.semantic_tags or "[]") == ["customer", "account"]
    assert json.loads(table_doc.business_terms or "[]") == ["member", "registration"]
    assert json.loads(table_doc.aliases or "[]") == ["customer_account"]
    assert table_doc.table_role == "dim"
    assert table_doc.grain == "one row per customer account"
    assert table_doc.subject_area == "user"
    assert table_doc.ai_confidence == 0.91
    assert "Customer account records" in table_doc.search_text
    assert "customer_account" in table_doc.search_text

    assert column_doc.ai_description == "Email address used as the customer login identifier."
    assert json.loads(column_doc.semantic_tags or "[]") == ["email", "login"]
    assert json.loads(column_doc.business_terms or "[]") == ["contact email"]
    assert json.loads(column_doc.aliases or "[]") == ["login_email"]
    assert column_doc.column_role == "identifier"
    assert column_doc.metric_type == "dimension"
    assert column_doc.ai_confidence == 0.88
    assert "customer login identifier" in column_doc.search_text
