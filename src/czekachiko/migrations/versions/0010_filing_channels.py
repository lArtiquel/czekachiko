"""filing channels: in_person, post, mos and unknown; aggregates per channel

"paper" splits in two. People's paper cases become post (decided 2026-10-30; owners can
change it). Imported paper cases become unknown, and the next importer run reclassifies them
from the source. `cases.channel` is VARCHAR(16), which fits every new value.

Aggregates gain a channel: NULL is every channel (unknown included), the others hold one
channel each; unknown never gets rows of its own. Every row is recomputed here in SQL, so the
app has per-channel numbers right after the upgrade. percentile_cont interpolates like
stats.percentile, so the rows match what repo.recompute_all writes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

OLD_KEY = "aggregates_voivodeship_purpose_from_m_to_m_key"
NEW_KEY = "aggregates_voivodeship_purpose_channel_from_m_to_m_key"
# domain.INTERVAL_PAIRS as of this revision.
PAIRS = (
    ("filed", "case_number"),
    ("filed", "braki"),
    ("filed", "fingerprints"),
    ("filed", "decision"),
    ("filed", "card"),
    ("fingerprints", "decision"),
    ("decision", "card"),
)

RECOMPUTE = """
WITH iv AS (
    SELECT c.voivodeship, c.purpose, c.channel, a.milestone AS from_m, b.milestone AS to_m,
           (b.date - a.date) AS days
    FROM milestones a
    JOIN milestones b ON b.case_id = a.case_id
    JOIN cases c ON c.id = a.case_id
    WHERE (a.milestone, b.milestone) IN ({pairs})
), keyed AS (
    SELECT voivodeship, purpose, CAST(NULL AS varchar) AS channel, from_m, to_m, days FROM iv
    UNION ALL
    SELECT voivodeship, purpose, channel, from_m, to_m, days FROM iv WHERE channel <> 'unknown'
)
INSERT INTO aggregates
    (voivodeship, purpose, channel, from_m, to_m, n, p10, median, p90, min, max, mean)
SELECT voivodeship, purpose, channel, from_m, to_m, count(*),
       percentile_cont(0.1) WITHIN GROUP (ORDER BY days),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY days),
       percentile_cont(0.9) WITHIN GROUP (ORDER BY days),
       min(days), max(days), CAST(avg(days) AS double precision)
FROM keyed
GROUP BY GROUPING SETS ((voivodeship, purpose, channel, from_m, to_m),
                        (purpose, channel, from_m, to_m))
"""


def upgrade() -> None:
    op.execute("UPDATE cases SET channel = 'post' WHERE channel = 'paper' AND source = 'user'")
    op.execute("UPDATE cases SET channel = 'unknown' WHERE channel = 'paper'")
    op.add_column("aggregates", sa.Column("channel", sa.String(16), nullable=True))
    op.drop_constraint(OLD_KEY, "aggregates", type_="unique")
    op.execute(
        f"ALTER TABLE aggregates ADD CONSTRAINT {NEW_KEY} "
        "UNIQUE NULLS NOT DISTINCT (voivodeship, purpose, channel, from_m, to_m)"
    )
    op.execute("DELETE FROM aggregates")
    op.execute(RECOMPUTE.format(pairs=", ".join(f"('{a}', '{b}')" for a, b in PAIRS)))


def downgrade() -> None:
    op.execute("DELETE FROM aggregates WHERE channel IS NOT NULL")
    op.drop_constraint(NEW_KEY, "aggregates", type_="unique")
    op.drop_column("aggregates", "channel")
    op.execute(
        f"ALTER TABLE aggregates ADD CONSTRAINT {OLD_KEY} "
        "UNIQUE NULLS NOT DISTINCT (voivodeship, purpose, from_m, to_m)"
    )
    op.execute("UPDATE cases SET channel = 'paper' WHERE channel <> 'mos'")
