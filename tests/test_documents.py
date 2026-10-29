from datetime import date

import pytest
from sqlalchemy import func, select

from czekachiko import documents
from czekachiko.db import repo
from czekachiko.db.models import AggregateRow, CaseDocument, OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales import en, ru
from czekachiko.stats import Forecast
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Act, Nav, Pick

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


# --- screens -------------------------------------------------------------------------

MENU = Nav(to="menu").pack()


class FakeCase:
    id = 7
    voivodeship = "mazowieckie"
    purpose = "jdg"
    channel = "mos"

    def dates(self):
        return {Milestone.filed: FILED}


def buttons(kb):
    return [b for row in kb.inline_keyboard for b in row]


def datas(kb):
    return {b.callback_data for b in buttons(kb)}


ROWS = [Row(code="wniosek", submitted_on=FILED, id=1), Row(name="Wyciąg z banku", id=2)]


def test_docs_view_lists_the_purpose_checklist():
    text, kb = screens.docs_view("ru", FakeCase(), ROWS)
    labels = [b.text for b in buttons(kb)]
    for code in documents.checklist("jdg"):
        assert any(documents.doc_name(code) in label for label in labels)
    assert "✅ Wniosek" in labels and "⬜ Zdjęcia" in labels and "⬜ Wyciąg z banku" in labels
    # The text carries the dates (it wraps; buttons truncate) and only for what was sent.
    assert "✅ Wniosek — 06.03.2026" in text
    assert "Zdjęcia" not in text and "Wyciąg z banku" not in text
    assert ru.MESSAGES["docs_note"] in text  # typical list, check with your urząd
    assert f"1 из {len(documents.checklist('jdg')) + 1}" in text
    assert Pick(field="doc", value="wniosek", case_id=7).pack() in datas(kb)
    assert Pick(field="doc", value="2", case_id=7).pack() in datas(kb)
    assert Act(action="doc_add", case_id=7).pack() in datas(kb)
    assert {Nav(to="case", case_id=7).pack(), MENU} <= datas(kb)


def test_docs_view_escapes_custom_names_in_text_only():
    rows = [Row(name="<b>bold</b> & <a href='x'>", submitted_on=FILED, id=3)]
    text, kb = screens.docs_view("ru", FakeCase(), rows)
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; &lt;a href=&#x27;x&#x27;&gt;" in text
    assert "<b>bold</b>" not in text and "<a href" not in text
    # Button labels are plain text in Telegram: escaping them would show the entities.
    assert any(b.text.endswith("<b>bold</b> & <a href='x'>") for b in buttons(kb))


def test_docs_view_notice_on_top():
    text, _ = screens.docs_view("ru", FakeCase(), [], notice="⚠️ limit")
    assert text.startswith("⚠️ limit")


FC = Forecast(kind="no_data", anchor=Milestone.filed, target=Milestone.fingerprints)


def test_case_view_shows_document_progress_and_button():
    text, kb = screens.case_view("ru", FakeCase(), FC, docs=(5, 9))
    assert "📋 Документы: 5/9" in text
    assert Nav(to="docs", case_id=7).pack() in datas(kb)
    en_text, _ = screens.case_view("en", FakeCase(), FC, docs=(5, 9))
    assert "📋 Documents: 5/9" in en_text


def test_case_view_without_docs_has_no_progress_line():
    text, kb = screens.case_view("ru", FakeCase(), FC)
    assert "📋" not in text
    assert Nav(to="docs", case_id=7).pack() in datas(kb)


def doc_screens(lang):
    case, doc = FakeCase(), Row(name="<i>x</i>", submitted_on=FILED, id=99)
    return [
        screens.docs_view(lang, case, ROWS),
        screens.doc_item_view(lang, case.id, doc),
        screens.doc_name_prompt(lang, case.id),
        screens.doc_name_prompt(lang, case.id, rename=True, error="⚠️"),
        screens.doc_date_prompt(lang, case.id, "<i>x</i>", 2026, 3, TODAY, can_clear=True),
        screens.confirm_delete_doc(lang, case.id, doc),
    ]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_document_screens_have_back_and_menu_and_escape(lang):
    back = {Nav(to="docs", case_id=7).pack(), Nav(to="case", case_id=7).pack()}
    for text, kb in doc_screens(lang):
        assert MENU in datas(kb), text[:40]
        assert back & datas(kb), text[:40]
        assert "<i>x</i>" not in text, text[:40]
        assert all(len(d.encode()) <= 64 for d in datas(kb) if d)


def test_input_screens_have_cancel():
    cancel = Act(action="cancel").pack()
    _, name_kb = screens.doc_name_prompt("ru", 7)
    _, date_kb = screens.doc_date_prompt("ru", 7, "Wniosek", 2026, 3, TODAY)
    assert cancel in datas(name_kb) and cancel in datas(date_kb)


def test_doc_date_prompt_clear_button_only_when_ticked():
    clear = Act(action="clear_date").pack()
    assert clear in datas(screens.doc_date_prompt("ru", 7, "W", 2026, 3, TODAY, can_clear=True)[1])
    assert clear not in datas(screens.doc_date_prompt("ru", 7, "W", 2026, 3, TODAY)[1])


def test_doc_item_view_actions():
    doc = Row(name="Wyciąg", submitted_on=FILED, id=99)
    text, kb = screens.doc_item_view("ru", 7, doc)
    assert "Wyciąg" in text and "06.03.2026" in text
    for action in ("doc_date", "doc_ren", "doc_del"):
        assert Act(action=action, case_id=7, value="99").pack() in datas(kb)


def test_privacy_mentions_documents():
    assert "документ" in ru.MESSAGES["privacy"]
    assert "document" in en.MESSAGES["privacy"]
