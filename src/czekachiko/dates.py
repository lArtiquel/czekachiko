import re
from collections.abc import Mapping
from datetime import date

from czekachiko.domain import ORDERED_CHAIN, Milestone

EARLIEST = date(2015, 1, 1)
_DMY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_date(text: str, today: date) -> date | None:
    """Parse DD.MM.YYYY, D.M.YYYY or YYYY-MM-DD; None for anything else."""
    text = text.strip()
    if m := _DMY.match(text):
        d, mo, y = map(int, m.groups())
    elif m := _ISO.match(text):
        y, mo, d = map(int, m.groups())
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def validate_milestones(dates: Mapping[Milestone, date], today: date) -> list[str]:
    """Error codes for a case's milestone dates; empty list when valid."""
    filed = dates.get(Milestone.filed)
    if filed is None:
        return ["filed_missing"]
    errors: list[str] = []
    if any(d > today for d in dates.values()):
        errors.append("future")
    if filed < EARLIEST:
        errors.append("before_2015")
    if any(d < filed for m, d in dates.items() if m != Milestone.filed):
        errors.append("before_filed")
    chain = [dates[m] for m in ORDERED_CHAIN if m in dates]
    if any(a > b for a, b in zip(chain, chain[1:], strict=False)):
        errors.append("order")
    return errors
