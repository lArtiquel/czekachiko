from datetime import date

import pytest

from czekachiko.dates import parse_date, validate_milestones
from czekachiko.domain import INTERVAL_PAIRS, Milestone, Purpose, Voivodeship

M = Milestone
TODAY = date(2026, 10, 29)


@pytest.mark.parametrize("text", ["06.03.2026", "6.3.2026", "2026-03-06", " 06.03.2026 "])
def test_parse_date_accepts_formats(text):
    assert parse_date(text, TODAY) == date(2026, 3, 6)


GARBAGE = ["завтра", "31.02.2026", "", "06/03/2026", "2026-13-01", "Mazowieckie"]


@pytest.mark.parametrize("text", GARBAGE)
def test_parse_date_rejects_garbage(text):
    assert parse_date(text, TODAY) is None


def test_valid_case_has_no_errors():
    assert validate_milestones({M.filed: date(2026, 3, 6), M.fingerprints: TODAY}, TODAY) == []


def test_future_date_rejected():
    assert validate_milestones({M.filed: date(2026, 10, 30)}, TODAY) == ["future"]


def test_before_2015_rejected():
    assert validate_milestones({M.filed: date(2014, 12, 31)}, TODAY) == ["before_2015"]


def test_decision_before_fingerprints_rejected():
    errors = validate_milestones(
        {M.filed: date(2026, 1, 1), M.fingerprints: date(2026, 6, 1), M.decision: date(2026, 5, 1)},
        TODAY,
    )
    assert errors == ["order"]


def test_edit_filed_after_fingerprints_rejected():
    errors = validate_milestones(
        {M.filed: date(2026, 11, 1), M.fingerprints: date(2026, 10, 29)}, date(2026, 11, 5)
    )
    assert "before_filed" in errors


def test_filed_missing():
    assert validate_milestones({M.fingerprints: TODAY}, TODAY) == ["filed_missing"]


def test_enums_and_pairs():
    assert len(Voivodeship) == 16
    assert [p.value for p in Purpose] == [
        "praca",
        "jdg",
        "studia",
        "rodzina",
        "inne",
        "blue_card",
        "staly",
        "rezydent_ue",
    ]
    assert (M.fingerprints, M.decision) in INTERVAL_PAIRS
    assert len(INTERVAL_PAIRS) == 7
    assert (M.filed, M.braki) in INTERVAL_PAIRS
