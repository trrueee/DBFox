import pytest
from sqlalchemy.exc import IntegrityError
from engine.models import Project, DataSource


def test_unique_constraints_enforcement(db_session) -> None:
    """Verify unique constraints: project name, datasource (project_id, name)."""
    db = db_session

    # 1. Project name uniqueness
    p1 = Project(name="Sprint-Test-Project")
    db.add(p1)
    db.commit()

    p2 = Project(name="Sprint-Test-Project")
    db.add(p2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Clean up
    db.delete(p1)
    db.commit()

    # 2. DataSource uniqueness on project_id and name
    proj = Project(name="Sprint-Unique-DS-Proj")
    db.add(proj)
    db.commit()

    ds1 = DataSource(
        project_id=proj.id,
        name="DS-Unique",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="test_db",
        username="root",
        connection_generation=1,
    )
    db.add(ds1)
    db.commit()

    ds2 = DataSource(
        project_id=proj.id,
        name="DS-Unique",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="test_db",
        username="root",
        connection_generation=1,
    )
    db.add(ds2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Clean up
    db.delete(ds1)
    db.delete(proj)
    db.commit()
