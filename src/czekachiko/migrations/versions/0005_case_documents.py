"""case documents checklist"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(32)),
        sa.Column("name", sa.String(60)),
        sa.Column("submitted_on", sa.Date),
        # (case_id, code) also serves lookups by case_id, so no separate index.
        sa.UniqueConstraint("case_id", "code", name="uq_case_documents_code"),
        sa.CheckConstraint("(code IS NULL) <> (name IS NULL)", name="ck_case_documents_kind"),
        sa.CheckConstraint("name IS NULL OR btrim(name) <> ''", name="ck_case_documents_name"),
    )


def downgrade() -> None:
    op.drop_table("case_documents")
