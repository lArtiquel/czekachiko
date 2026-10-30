"""where a case came from: 'user' or an importer such as 'pobytrack'"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases", sa.Column("source", sa.String(32), nullable=False, server_default="user")
    )
    op.create_index("ix_cases_source", "cases", ["source"])
    op.execute("UPDATE cases SET source = 'pobytrack' WHERE client_token LIKE 'pobytrack:%'")


def downgrade() -> None:
    op.drop_index("ix_cases_source", table_name="cases")
    op.drop_column("cases", "source")
