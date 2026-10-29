from datetime import date

import pytest

from czekachiko import documents
from czekachiko.domain import Purpose

TODAY = date(2026, 10, 29)
FILED = date(2026, 3, 6)
CORE = ("wniosek", "zdjecia", "paszport", "oplata", "ubezpieczenie", "lokal")


# --- standard lists ----------------------------------------------------------------


@pytest.mark.parametrize("purpose", list(Purpose))
def test_every_purpose_has_a_short_typical_list(purpose):
    codes = documents.checklist(purpose)
    assert 6 <= len(codes) <= 10
    assert len(set(codes)) == len(codes)
    assert codes[: len(CORE)] == CORE
    assert all(documents.doc_name(c) for c in codes)


@pytest.mark.parametrize(
    ("purpose", "specific"),
    [
        (Purpose.praca, {"zalacznik1", "umowa_praca"}),
        (Purpose.jdg, {"ceidg", "pit", "zus"}),
        (Purpose.studia, {"uczelnia"}),
        (Purpose.rodzina, {"akt_rodzina"}),
    ],
)
def test_purpose_specific_items(purpose, specific):
    assert specific <= set(documents.checklist(purpose))


def test_names_are_polish():
    assert documents.doc_name("zalacznik1") == "Załącznik nr 1"
    assert documents.doc_name("ceidg") == "Wpis do CEIDG"
    assert documents.doc_name("lokal").startswith("Tytuł prawny do lokalu")


def test_unknown_purpose_string_raises():
    with pytest.raises(ValueError):
        documents.checklist("nope")


# --- custom names --------------------------------------------------------------------


def test_clean_name_strips_and_collapses_whitespace():
    assert documents.clean_name("  Zaświadczenie \n z  banku\t") == ("Zaświadczenie z banku", None)


def test_clean_name_drops_control_characters():
    assert documents.clean_name("PIT\x00-37\x07") == ("PIT-37", None)


def test_clean_name_accepts_exactly_60():
    assert documents.clean_name("a" * 60) == ("a" * 60, None)


def test_clean_name_rejects_61():
    assert documents.clean_name("a" * 61) == (None, "doc_name_long")


@pytest.mark.parametrize("text", ["", "   ", "\n\t ", "\x00"])
def test_clean_name_rejects_empty(text):
    assert documents.clean_name(text) == (None, "doc_name_empty")


# --- dates ---------------------------------------------------------------------------


def test_date_today_and_filing_day_ok():
    assert documents.date_error(TODAY, FILED, TODAY) is None
    assert documents.date_error(FILED, FILED, TODAY) is None


def test_future_date_rejected():
    assert documents.date_error(date(2026, 10, 30), FILED, TODAY) == "future"


def test_date_margin_before_filing():
    assert documents.earliest(FILED) == date(2026, 2, 4)
    assert documents.date_error(date(2026, 2, 4), FILED, TODAY) is None
    assert documents.date_error(date(2026, 2, 3), FILED, TODAY) == "doc_too_early"


# --- progress ------------------------------------------------------------------------


class Row:
    def __init__(self, code=None, name=None, submitted_on=None):
        self.code, self.name, self.submitted_on = code, name, submitted_on


def test_progress_counts_standard_and_custom():
    rows = [
        Row(code="wniosek", submitted_on=FILED),
        Row(code="zdjecia", submitted_on=None),
        Row(code="retired_code", submitted_on=FILED),  # no longer in the list: ignored
        Row(name="Zaświadczenie z banku", submitted_on=FILED),
        Row(name="PIT-37"),
    ]
    total = len(documents.checklist(Purpose.jdg)) + 2
    assert documents.progress(Purpose.jdg, rows) == (2, total)
