import uuid

from engine.environment.schema_introspector import SchemaIntrospector
from engine.models import DataSource


def test_decrypt_datasource_password_does_not_query_sqlalchemy_bind(db_session):
    ds = DataSource(
        id=str(uuid.uuid4()),
        name="mysql probe",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="creatorhub",
        username="root",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    password = SchemaIntrospector()._decrypt_datasource_password(db_session, ds.id)

    assert password == ""
