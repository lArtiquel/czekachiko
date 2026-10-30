"""aggregates without impossible zero days from filing

A case number, a call or (anywhere but in person) fingerprints 0 days after filing is a
data-entry error, and statistics now leave such intervals out (domain.zero_day_possible).
Stored dates stay. Every aggregate row is recomputed here in SQL, as 0010 did, so the numbers
match what repo.recompute_all writes right after the upgrade; downgrade recomputes them with
the zeros back in.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

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
# repo._possible_sql() as of this revision.
POSSIBLE = (
    "NOT (a.milestone = 'filed' AND b.date = a.date AND ((b.milestone = 'case_number') "
    "OR (b.milestone = 'braki') "
    "OR (b.milestone = 'fingerprints' AND c.channel NOT IN ('in_person'))))"
)

# 0010's recompute with a filter on the intervals.
RECOMPUTE = """
WITH iv AS (
    SELECT c.voivodeship, c.purpose, c.channel, a.milestone AS from_m, b.milestone AS to_m,
           (b.date - a.date) AS days
    FROM milestones a
    JOIN milestones b ON b.case_id = a.case_id
    JOIN cases c ON c.id = a.case_id
    WHERE (a.milestone, b.milestone) IN ({pairs}) AND {where}
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


def _recompute(where: str) -> None:
    op.execute("DELETE FROM aggregates")
    pairs = ", ".join(f"('{a}', '{b}')" for a, b in PAIRS)
    op.execute(RECOMPUTE.format(pairs=pairs, where=where))


def upgrade() -> None:
    _recompute(POSSIBLE)


def downgrade() -> None:
    _recompute("TRUE")
