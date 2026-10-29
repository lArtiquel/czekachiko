"""initial schema"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("tg_id", sa.BigInteger, primary_key=True),
        sa.Column("lang", sa.String(2), nullable=False, server_default="ru"),
        sa.Column("reminders", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tg_id",
            sa.BigInteger,
            sa.ForeignKey("users.tg_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("voivodeship", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("client_token", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "milestones",
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("milestone", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("confirmed_outlier", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "aggregates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("voivodeship", sa.String(32)),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("from_m", sa.String(16), nullable=False),
        sa.Column("to_m", sa.String(16), nullable=False),
        sa.Column("n", sa.Integer, nullable=False),
        sa.Column("p10", sa.Float, nullable=False),
        sa.Column("median", sa.Float, nullable=False),
        sa.Column("p90", sa.Float, nullable=False),
        sa.Column("min", sa.Integer, nullable=False),
        sa.Column("max", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "voivodeship", "purpose", "from_m", "to_m", postgresql_nulls_not_distinct=True
        ),
    )
    op.create_table(
        "fsm",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("state", sa.String(128)),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
    )
    op.create_table(
        "calendar_events",
        sa.Column("case_id", sa.Integer, primary_key=True),
        sa.Column("milestone", sa.String(16), primary_key=True),
        sa.Column("event_id", sa.String(256), nullable=False),
    )
    op.create_table(
        "calendar_outbox",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("op", sa.String(8), nullable=False),
        sa.Column("case_id", sa.Integer, nullable=False, index=True),
        sa.Column("milestone", sa.String(16), nullable=False),
        sa.Column("payload", JSONB),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_try_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("op in ('upsert', 'delete')", name="ck_outbox_op"),
    )


def downgrade() -> None:
    for t in ["calendar_outbox", "calendar_events", "fsm", "aggregates", "milestones", "cases"]:
        op.drop_table(t)
    op.drop_table("users")
