"""feedback: media kind; admin replies keep their message id"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("media", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("feedback", "media")
