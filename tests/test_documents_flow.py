"""Document checklist driven through the dispatcher, as a Telegram user would."""

from datetime import date

import pytest
from aiogram.methods import AnswerInlineQuery
from aiogram.types import Chat, InlineQuery, Message, Update
from sqlalchemy import func, select

from czekachiko import documents
from czekachiko.app import build_dispatcher
from czekachiko.db import repo
from czekachiko.db.models import CaseDocument, OutboxRow
from czekachiko.domain import Channel, Purpose, Voivodeship
from czekachiko.locales import ru
from czekachiko.ui.keyboards import Act, Day, Nav, Pick
from tests.fakes import NOW, _ids, _user, callback_update, make_bot, text_update

UID, OTHER = 548, 549
TODAY = date(2026, 10, 29)
FILED = date(2026, 3, 6)
JDG_TOTAL = len(documents.checklist(Purpose.jdg))


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(session_factory, clock=lambda: TODAY, throttle=False, ephemeral_delay=0)
    return dp, bot, tg, session_factory


async def tap(env, data, uid=UID):
    await env[0].feed_update(env[1], callback_update(uid, data.pack()))


async def say(env, text, uid=UID):
    await env[0].feed_update(env[1], text_update(uid, text))


def last(env):
    return env[2].last()


def datas(env) -> set[str]:
    return {b.callback_data for row in last(env).reply_markup.inline_keyboard for b in row}


def labels(env) -> list[str]:
    return [b.text for row in last(env).reply_markup.inline_keyboard for b in row]


def in_menu(env) -> bool:
    return last(env).text == ru.MESSAGES["menu_title"]


async def make_case(env, uid=UID, token="mine") -> int:
    async with env[3]() as s:
        await repo.ensure_user(s, uid)
        c = await repo.create_case(
            s, uid, Voivodeship.mazowieckie, Purpose.jdg, Channel.mos, FILED, token
        )
        await s.commit()
        return c.id


async def add_custom(env, case_id, name, uid=UID, d=FILED) -> int:
    async with env[3]() as s:
        case = await repo.get_case(s, uid, case_id)
        doc = await repo.add_custom_doc(s, case, name, d)
        await s.commit()
        return doc.id


async def docs_of(env, case_id, uid=UID) -> dict:
    async with env[3]() as s:
        case = await repo.get_case(s, uid, case_id)
        return {(d.code or d.name): d.submitted_on for d in await repo.list_docs(s, case)}


async def all_docs(env) -> int:
    async with env[3]() as s:
        return await s.scalar(select(func.count()).select_from(CaseDocument))


# --- entry point ---------------------------------------------------------------------


async def test_case_screen_has_docs_button_and_progress(env):
    cid = await make_case(env)
    await tap(env, Nav(to="case", case_id=cid))
    assert f"📋 Документы: 0/{JDG_TOTAL}" in last(env).text
    assert Nav(to="docs", case_id=cid).pack() in datas(env)


async def test_docs_screen_lists_the_checklist(env):
    cid = await make_case(env)
    await tap(env, Nav(to="docs", case_id=cid))
    assert ru.MESSAGES["docs_note"] in last(env).text
    assert "⬜ Wpis do CEIDG" in labels(env)
    assert Act(action="doc_add", case_id=cid).pack() in datas(env)


# --- standard items: tick, re-date, un-tick ------------------------------------------


async def test_tick_standard_item_with_a_date(env):
    cid = await make_case(env)
    await tap(env, Nav(to="docs", case_id=cid))
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    assert Day(y=2026, m=3, d=6).pack() in datas(env)  # the picker opens on the filing month
    assert Act(action="clear_date").pack() not in datas(env)
    await tap(env, Day(y=2026, m=3, d=6))
    assert await docs_of(env, cid) == {"wniosek": FILED}
    assert "✅ Wniosek — 06.03.2026" in last(env).text
    assert f"отправлено 1 из {JDG_TOTAL}" in last(env).text
    await tap(env, Nav(to="case", case_id=cid))
    assert f"📋 Документы: 1/{JDG_TOTAL}" in last(env).text


async def test_redate_standard_item(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await tap(env, Day(y=2026, m=3, d=6))
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    assert Act(action="clear_date").pack() in datas(env)
    await tap(env, Day(y=2026, m=3, d=9))
    assert await docs_of(env, cid) == {"wniosek": date(2026, 3, 9)}


async def test_untick_standard_item(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await tap(env, Day(y=2026, m=3, d=6))
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await tap(env, Act(action="clear_date"))
    assert await docs_of(env, cid) == {}
    assert "⬜ Wniosek" in labels(env)


async def test_typed_date_accepted(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="paszport", case_id=cid))
    await say(env, "06.03.2026")
    assert await docs_of(env, cid) == {"paszport": FILED}


@pytest.mark.parametrize(
    "send",
    [
        lambda env: say(env, "30.10.2026"),
        lambda env: tap(env, Day(y=2026, m=10, d=30)),  # forged: the picker never offers it
    ],
)
async def test_future_date_rejected(env, send):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await send(env)
    assert ru.MESSAGES["err_future"] in last(env).text
    assert await docs_of(env, cid) == {}


async def test_date_long_before_filing_rejected(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await say(env, "03.02.2026")
    assert "04.02.2026" in last(env).text
    assert await docs_of(env, cid) == {}
    await say(env, "04.02.2026")
    assert await docs_of(env, cid) == {"wniosek": date(2026, 2, 4)}


async def test_garbage_date_rejected(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await say(env, "вчера вроде")
    assert ru.MESSAGES["err_not_date"] in last(env).text


async def test_item_from_another_purpose_refused(env):
    cid = await make_case(env)  # jdg
    await tap(env, Pick(field="doc", value="zalacznik1", case_id=cid))
    assert in_menu(env)


async def test_back_from_picker_returns_to_checklist(env):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    assert Nav(to="docs", case_id=cid).pack() in datas(env)
    await tap(env, Nav(to="docs", case_id=cid))
    await say(env, "06.03.2026")  # no longer picking: not saved
    assert await docs_of(env, cid) == {}


# --- custom items --------------------------------------------------------------------


async def test_add_custom_document(env):
    cid = await make_case(env)
    await tap(env, Nav(to="docs", case_id=cid))
    await tap(env, Act(action="doc_add", case_id=cid))
    assert Act(action="cancel").pack() in datas(env)
    await say(env, "  Zaświadczenie   z banku ")
    assert "Zaświadczenie z banku" in last(env).text  # the date prompt names it
    await tap(env, Day(y=2026, m=4, d=1))
    assert await docs_of(env, cid) == {"Zaświadczenie z banku": date(2026, 4, 1)}
    assert "✅ Zaświadczenie z banku — 01.04.2026" in last(env).text
    assert f"отправлено 1 из {JDG_TOTAL + 1}" in last(env).text


async def test_61_char_name_rejected_then_60_accepted(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    await say(env, "a" * 61)
    assert ru.MESSAGES["err_doc_name_long"].format(max=60) in last(env).text
    await say(env, "b" * 60)
    await tap(env, Day(y=2026, m=4, d=1))
    assert await docs_of(env, cid) == {"b" * 60: date(2026, 4, 1)}


async def test_whitespace_name_rejected(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    await say(env, "   \n  ")
    assert ru.MESSAGES["err_doc_name_empty"] in last(env).text
    assert await all_docs(env) == 0


async def test_non_text_name_rejected(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    msg = Message(
        message_id=next(_ids), date=NOW, chat=Chat(id=UID, type="private"), from_user=_user(UID)
    )
    await env[0].feed_update(env[1], Update(update_id=next(_ids), message=msg))
    assert ru.MESSAGES["err_doc_text_only"] in last(env).text


async def test_html_in_a_name_is_escaped_on_render(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    await say(env, "<b>PIT</b> & <a href='https://x.example'>")
    assert "<b>PIT</b>" not in last(env).text and "&lt;b&gt;PIT&lt;/b&gt;" in last(env).text
    await tap(env, Day(y=2026, m=4, d=1))
    text = last(env).text
    assert "&lt;b&gt;PIT&lt;/b&gt; &amp; &lt;a href=" in text
    assert "<b>PIT</b>" not in text and "<a href" not in text
    assert await docs_of(env, cid) == {
        "<b>PIT</b> & <a href='https://x.example'>": date(2026, 4, 1)
    }


async def test_sixteenth_custom_document_rejected(env):
    cid = await make_case(env)
    for i in range(documents.MAX_CUSTOM):
        await add_custom(env, cid, f"Dokument {i}")
    await tap(env, Act(action="doc_add", case_id=cid))
    assert ru.MESSAGES["doc_limit"].format(max=15) in last(env).text
    await say(env, "Dokument 16")  # not asking for a name: ignored
    assert await all_docs(env) == 15


async def test_rename_custom_document(env):
    cid = await make_case(env)
    doc_id = await add_custom(env, cid, "Wyciąg")
    await tap(env, Pick(field="doc", value=str(doc_id), case_id=cid))
    assert Act(action="doc_ren", case_id=cid, value=str(doc_id)).pack() in datas(env)
    await tap(env, Act(action="doc_ren", case_id=cid, value=str(doc_id)))
    await say(env, "a" * 61)
    assert ru.MESSAGES["err_doc_name_long"].format(max=60) in last(env).text
    await say(env, "Wyciąg z konta")
    assert await docs_of(env, cid) == {"Wyciąg z konta": FILED}


async def test_redate_and_untick_custom_document(env):
    cid = await make_case(env)
    doc_id = await add_custom(env, cid, "Wyciąg")
    await tap(env, Pick(field="doc", value=str(doc_id), case_id=cid))
    await tap(env, Act(action="doc_date", case_id=cid, value=str(doc_id)))
    await tap(env, Day(y=2026, m=5, d=5))
    assert await docs_of(env, cid) == {"Wyciąg": date(2026, 5, 5)}
    await tap(env, Act(action="doc_date", case_id=cid, value=str(doc_id)))
    await tap(env, Act(action="clear_date"))
    assert await docs_of(env, cid) == {"Wyciąg": None}


async def test_delete_custom_document(env):
    cid = await make_case(env)
    doc_id = await add_custom(env, cid, "Wyciąg")
    await tap(env, Act(action="doc_del", case_id=cid, value=str(doc_id)))
    assert "Wyciąg" in last(env).text
    await tap(env, Act(action="doc_del_yes", case_id=cid, value=str(doc_id)))
    assert await docs_of(env, cid) == {}
    assert ru.MESSAGES["docs_note"] in last(env).text


async def test_cancel_while_naming_saves_nothing(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    await tap(env, Act(action="cancel"))
    assert in_menu(env)
    await say(env, "Wyciąg")
    assert await all_docs(env) == 0


# --- ownership -----------------------------------------------------------------------


async def test_another_users_case_is_refused(env):
    theirs = await make_case(env, uid=OTHER, token="theirs")
    await add_custom(env, theirs, "Cudzy", uid=OTHER)
    for data in [
        Nav(to="docs", case_id=theirs),
        Pick(field="doc", value="wniosek", case_id=theirs),
        Act(action="doc_add", case_id=theirs),
    ]:
        await tap(env, data)
        assert in_menu(env), data
    assert await docs_of(env, theirs, uid=OTHER) == {"Cudzy": FILED}


async def test_another_cases_item_is_refused(env):
    mine = await make_case(env)
    theirs = await make_case(env, uid=OTHER, token="theirs")
    doc_id = str(await add_custom(env, theirs, "Cudzy", uid=OTHER))
    for case_id in (mine, theirs):
        for data in [
            Pick(field="doc", value=doc_id, case_id=case_id),
            Act(action="doc_date", case_id=case_id, value=doc_id),
            Act(action="doc_ren", case_id=case_id, value=doc_id),
            Act(action="doc_del", case_id=case_id, value=doc_id),
            Act(action="doc_del_yes", case_id=case_id, value=doc_id),
        ]:
            await tap(env, data)
            assert in_menu(env), data
    assert await docs_of(env, theirs, uid=OTHER) == {"Cudzy": FILED}


@pytest.mark.parametrize("value", ["99999999999999", "٣", "-1", ""])
async def test_malformed_item_ids_fall_back_to_menu(env, value):
    cid = await make_case(env)
    await tap(env, Pick(field="doc", value=value, case_id=cid))
    assert in_menu(env)


async def test_case_deleted_mid_flow(env):
    cid = await make_case(env)
    await tap(env, Act(action="doc_add", case_id=cid))
    await tap(env, Act(action="del_case_yes", case_id=cid))
    await tap(env, Act(action="doc_add", case_id=cid))
    assert in_menu(env)


# --- documents stay private ----------------------------------------------------------


async def test_share_card_has_no_documents(env):
    cid = await make_case(env)
    await add_custom(env, cid, "SECRET-XYZ")
    async with env[3]() as s:
        await repo.set_standard_doc(s, await repo.get_case(s, UID, cid), "wniosek", FILED)
        await s.commit()
    iq = InlineQuery(id=str(next(_ids)), from_user=_user(UID), query=f"c:{cid}", offset="")
    await env[0].feed_update(env[1], Update(update_id=next(_ids), inline_query=iq))
    (answer,) = [c for c in env[2].calls if isinstance(c, AnswerInlineQuery)]
    text = answer.results[0].input_message_content.message_text
    assert "Mazowieckie" in text
    assert "SECRET-XYZ" not in text and "📋" not in text and "Документы" not in text


async def test_document_flows_leave_the_calendar_outbox_alone(env):
    cid = await make_case(env)

    async def outbox():
        async with env[3]() as s:
            return (await s.execute(select(OutboxRow.id, OutboxRow.payload))).all()

    before = await outbox()
    await tap(env, Pick(field="doc", value="wniosek", case_id=cid))
    await tap(env, Day(y=2026, m=3, d=6))
    await tap(env, Act(action="doc_add", case_id=cid))
    await say(env, "SECRET-XYZ")
    await tap(env, Day(y=2026, m=4, d=1))
    assert await outbox() == before
    assert "SECRET-XYZ" not in str(before)
