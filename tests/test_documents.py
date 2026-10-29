from datetime import date

import pytest
from sqlalchemy import func, select

from czekachiko import documents
from czekachiko.db import repo
from czekachiko.db.models import AggregateRow, CaseDocument, OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

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
    def __init__(self, code=None, name=None, submitted_on=None, id=0):
        self.code, self.name, self.submitted_on, self.id = code, name, submitted_on, id


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


# --- repository ----------------------------------------------------------------------


async def make_case(s, tg_id=1, token="tok", purpose=Purpose.jdg):
    await repo.ensure_user(s, tg_id)
    return await repo.create_case(
        s, tg_id, Voivodeship.mazowieckie, purpose, Channel.mos, FILED, token
    )


async def doc_dates(s, case) -> dict:
    return {(d.code or d.name): d.submitted_on for d in await repo.list_docs(s, case)}


async def test_standard_doc_tick_redate_untick(session):
    case = await make_case(session)
    await repo.set_standard_doc(session, case, "wniosek", FILED)
    assert await doc_dates(session, case) == {"wniosek": FILED}
    await repo.set_standard_doc(session, case, "wniosek", date(2026, 3, 9))
    assert await doc_dates(session, case) == {"wniosek": date(2026, 3, 9)}
    await repo.set_standard_doc(session, case, "wniosek", None)
    assert await doc_dates(session, case) == {}


async def test_standard_code_must_belong_to_the_purpose(session):
    case = await make_case(session, purpose=Purpose.jdg)
    with pytest.raises(ValueError):
        await repo.set_standard_doc(session, case, "zalacznik1", FILED)  # praca only


async def test_add_custom_doc_and_limit(session):
    case = await make_case(session)
    for i in range(documents.MAX_CUSTOM):
        await repo.add_custom_doc(session, case, f"Dokument {i}", FILED)
    assert await repo.count_custom_docs(session, case) == 15
    with pytest.raises(repo.TooManyDocs):
        await repo.add_custom_doc(session, case, "Dokument 16", FILED)
    assert await repo.count_custom_docs(session, case) == 15


async def test_custom_doc_name_is_validated_by_the_repo_too(session):
    case = await make_case(session)
    with pytest.raises(ValueError):
        await repo.add_custom_doc(session, case, "a" * 61, FILED)
    with pytest.raises(ValueError):
        await repo.add_custom_doc(session, case, "   ", FILED)


async def test_custom_doc_rename_redate_untick_delete(session):
    case = await make_case(session)
    doc = await repo.add_custom_doc(session, case, "  Zaświadczenie  z banku ", FILED)
    assert doc.name == "Zaświadczenie z banku"
    await repo.rename_custom_doc(session, doc, "Wyciąg z banku")
    await repo.set_doc_date(session, doc, date(2026, 4, 1))
    assert await doc_dates(session, case) == {"Wyciąg z banku": date(2026, 4, 1)}
    await repo.set_doc_date(session, doc, None)
    assert await doc_dates(session, case) == {"Wyciąg z banku": None}
    await repo.delete_custom_doc(session, doc)
    assert await doc_dates(session, case) == {}


async def test_custom_doc_of_another_case_is_invisible(session):
    mine = await make_case(session, 1, "a")
    theirs = await make_case(session, 2, "b")
    doc = await repo.add_custom_doc(session, theirs, "Cudzy", FILED)
    assert await repo.get_custom_doc(session, mine, doc.id) is None
    assert (await repo.get_custom_doc(session, theirs, doc.id)).id == doc.id


async def count_docs(s) -> int:
    return await s.scalar(select(func.count()).select_from(CaseDocument))


async def test_deleting_a_case_deletes_its_documents(session):
    case = await make_case(session)
    await repo.set_standard_doc(session, case, "wniosek", FILED)
    await repo.add_custom_doc(session, case, "Własny", FILED)
    await session.commit()
    await repo.delete_case(session, case)
    await session.commit()
    assert await count_docs(session) == 0


async def test_deleting_the_user_deletes_their_documents(session):
    case = await make_case(session)
    await repo.add_custom_doc(session, case, "Własny", FILED)
    await session.commit()
    await repo.delete_user(session, 1)
    await session.commit()
    assert await count_docs(session) == 0


async def test_documents_touch_neither_aggregates_nor_calendar(session):
    case = await make_case(session)
    await repo.set_milestone(session, case, Milestone.fingerprints, date(2026, 6, 1))
    await session.commit()

    async def snapshot():
        aggs = (await session.execute(select(AggregateRow.id, AggregateRow.updated_at))).all()
        outbox = (await session.execute(select(OutboxRow.id, OutboxRow.payload))).all()
        return sorted(aggs), sorted(outbox, key=lambda r: r.id)

    before = await snapshot()
    await repo.set_standard_doc(session, case, "wniosek", FILED)
    doc = await repo.add_custom_doc(session, case, "SECRET-XYZ", FILED)
    await repo.rename_custom_doc(session, doc, "SECRET-ABC")
    await repo.delete_custom_doc(session, doc)
    await session.commit()
    assert await snapshot() == before
