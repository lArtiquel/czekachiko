"""per-voivodeship calendars"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("scope", sa.String(32), nullable=False, server_default="all"),
    )
    op.drop_constraint("calendar_events_pkey", "calendar_events", type_="primary")
    op.create_primary_key(
        "calendar_events_pkey", "calendar_events", ["case_id", "milestone", "scope"]
    )
    op.create_table(
        "calendars",
        sa.Column("scope", sa.String(32), primary_key=True),
        sa.Column("calendar_id", sa.String(256), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("calendars")
    op.execute("DELETE FROM calendar_events WHERE scope <> 'all'")
    op.drop_constraint("calendar_events_pkey", "calendar_events", type_="primary")
    op.create_primary_key("calendar_events_pkey", "calendar_events", ["case_id", "milestone"])
    op.drop_column("calendar_events", "scope")
