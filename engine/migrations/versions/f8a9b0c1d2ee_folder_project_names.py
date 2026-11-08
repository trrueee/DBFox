"""Folder projects use stable identity; different folders can share a name."""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2ee"
down_revision = "f7a8b9c0d0ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("uq_projects_name", type_="unique")


def downgrade() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "SELECT 1 FROM projects GROUP BY name HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError("Project names must be distinct before restoring the older schema.")
    with op.batch_alter_table("projects") as batch:
        batch.create_unique_constraint("uq_projects_name", ["name"])
