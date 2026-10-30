"""indexes for stats across several purposes and all of Poland

The new purposes (blue_card, staly, rezydent_ue) fit the existing VARCHAR(16) columns and
nothing constrains their values, so stored cases need no change. Stats for a permit-type
group or for all of Poland are computed from intervals on the fly; these indexes keep those
queries off sequential scans as the tables grow.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # purpose = ANY(...) with an optional voivodeship filter.
    op.create_index("ix_cases_purpose_voivodeship", "cases", ["purpose", "voivodeship"])
    # The anchor side of interval joins and who-now (milestone, date >= since).
    op.create_index("ix_milestones_milestone_date", "milestones", ["milestone", "date"])


def downgrade() -> None:
    op.drop_index("ix_milestones_milestone_date", table_name="milestones")
    op.drop_index("ix_cases_purpose_voivodeship", table_name="cases")
