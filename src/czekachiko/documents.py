"""Document checklist per purpose of stay: typical lists, custom names and date rules. Pure."""

import unicodedata
from collections.abc import Iterable
from datetime import date, timedelta

from czekachiko.domain import Purpose

P = Purpose
MAX_NAME = 60
MAX_CUSTOM = 15
# Documents go in with the application or later. The margin covers postal filing, where the
# recorded filing date is when the office received the envelope, and approximate dates.
MARGIN_DAYS = 30

# Polish names, the way applicants know them. Codes are what we store: never rename a code.
NAMES = {
    "wniosek": "Wniosek",
    "zdjecia": "Zdjęcia",
    "paszport": "Kopia paszportu",
    "oplata": "Opłata skarbowa",
    "ubezpieczenie": "Ubezpieczenie zdrowotne",
    "lokal": "Tytuł prawny do lokalu (umowa najmu)",
    "dochod": "Dokumenty potwierdzające dochód",
    "zalacznik1": "Załącznik nr 1",
    "umowa_praca": "Umowa o pracę / zlecenie",
    "ceidg": "Wpis do CEIDG",
    "pit": "PIT za ostatni rok",
    "zus": "Zaświadczenie z ZUS o niezaleganiu",
    "uczelnia": "Zaświadczenie z uczelni",
    "srodki": "Środki finansowe (wyciąg z konta)",
    "akt_rodzina": "Akt małżeństwa / urodzenia",
    "rodzina_pl": "Dokumenty członka rodziny w Polsce",
    "cel": "Dokumenty potwierdzające cel pobytu",
}

CORE = ("wniosek", "zdjecia", "paszport", "oplata", "ubezpieczenie", "lokal")
CHECKLISTS: dict[Purpose, tuple[str, ...]] = {
    P.praca: (*CORE, "zalacznik1", "umowa_praca", "dochod"),
    P.jdg: (*CORE, "ceidg", "pit", "zus"),
    P.studia: (*CORE, "uczelnia", "srodki"),
    P.rodzina: (*CORE, "akt_rodzina", "rodzina_pl", "dochod"),
    P.inne: (*CORE, "cel", "dochod"),
}


def checklist(purpose: Purpose | str) -> tuple[str, ...]:
    return CHECKLISTS[Purpose(purpose)]


def doc_name(code: str) -> str:
    return NAMES[code]


def clean_name(text: str) -> tuple[str | None, str | None]:
    """A custom document name: (cleaned, None) or (None, error code)."""
    collapsed = " ".join(text.split())  # newlines and tabs become single spaces
    if any(unicodedata.category(ch) in ("Cs", "Cn") for ch in collapsed):
        return None, "doc_name_empty"  # lone surrogates / unassigned code points: not a name
    name = "".join(ch for ch in collapsed if unicodedata.category(ch) != "Cc").strip()
    if not name:
        return None, "doc_name_empty"
    if len(name) > MAX_NAME:
        return None, "doc_name_long"
    return name, None


def earliest(filed: date) -> date:
    return filed - timedelta(days=MARGIN_DAYS)


def date_error(d: date, filed: date, today: date) -> str | None:
    if d > today:
        return "future"
    if d < earliest(filed):
        return "doc_too_early"
    return None


def progress(purpose: Purpose | str, rows: Iterable) -> tuple[int, int]:
    """(ticked, total) over the purpose's list plus the owner's own documents."""
    codes = set(checklist(purpose))
    rows = [r for r in rows if r.name is not None or r.code in codes]
    customs = sum(1 for r in rows if r.name is not None)
    return sum(1 for r in rows if r.submitted_on is not None), len(codes) + customs
