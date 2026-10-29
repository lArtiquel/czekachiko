"""feedback"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tg_id",
            sa.BigInteger,
            sa.ForeignKey("users.tg_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("admin_msg_id", sa.BigInteger, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("direction in ('in', 'out')", name="ck_feedback_direction"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
