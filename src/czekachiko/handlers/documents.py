"""Document checklist per case: the purpose's typical items plus the owner's own.

Every handler reaches a case through repo.get_case (owner check) and a custom document
only through that case. Custom names are free text and are shown only on these screens.
"""

from collections.abc import Callable
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko import documents
from czekachiko.dates import parse_date
from czekachiko.db import repo
from czekachiko.db.models import Case, CaseDocument
from czekachiko.domain import Milestone
from czekachiko.i18n import t
from czekachiko.render import show
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Act, Day, Month, Nav, Pick

router = Router(name="documents")
Clock = Callable[[], date]


class DocDate(StatesGroup):
    picking = State()


class DocName(StatesGroup):
    typing = State()


# --- helpers ---------------------------------------------------------------------------


async def docs_screen(s: AsyncSession, lang: str, case: Case, notice: str | None = None):
    return screens.docs_view(lang, case, await repo.list_docs(s, case), notice)


async def to_menu(event, state: FSMContext, lang: str) -> None:
    """Missing, foreign or stale ids all end here, like the global fallback."""
    await state.clear()
    await show(event, screens.main_menu(lang))


def parse_doc_id(value: str) -> int | None:
    # ASCII digits only, and small enough for an integer column.
    return int(value) if value.isascii() and value.isdigit() and len(value) <= 9 else None


async def owned_doc(
    s: AsyncSession, user_id: int, case_id: int, value: str
) -> tuple[Case | None, CaseDocument | None]:
    case = await repo.get_case(s, user_id, case_id)
    doc_id = parse_doc_id(value)
    if case is None or doc_id is None:
        return case, None
    return case, await repo.get_custom_doc(s, case, doc_id)


async def open_picker(
    event, state: FSMContext, lang: str, case: Case, today: date, target: dict, name: str, current
) -> None:
    """target: {"target": "std", "code"} | {"target": "custom", "doc_id"} | {"target": "new"}."""
    anchor = current or case.dates()[Milestone.filed]
    await state.set_state(DocDate.picking)
    await state.set_data(
        {
            "case_id": case.id,
            "name": name,
            "can_clear": current is not None,
            "pick_y": anchor.year,
            "pick_m": anchor.month,
            **target,
        }
    )
    await show_picker(event, state, lang, today)


async def show_picker(
    event,
    state: FSMContext,
    lang: str,
    today: date,
    error: str | None = None,
    month: tuple[int, int] | None = None,
) -> None:
    data = await state.get_data()
    if month is not None:
        await state.update_data(pick_y=month[0], pick_m=month[1])
    y, m = month or (data.get("pick_y", today.year), data.get("pick_m", today.month))
    case_id, name = int(data.get("case_id", 0)), data.get("name", "")
    can_clear = bool(data.get("can_clear"))
    await show(event, screens.doc_date_prompt(lang, case_id, name, y, m, today, can_clear, error))


# --- checklist and items ---------------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "docs"))
async def docs(
    cq: CallbackQuery, callback_data: Nav, session: AsyncSession, state: FSMContext, lang: str
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    if case is None:
        await to_menu(cq, state, lang)
        return
    await state.clear()
    await show(cq, await docs_screen(session, lang, case))


@router.callback_query(Pick.filter(F.field == "doc"))
async def pick_doc(
    cq: CallbackQuery,
    callback_data: Pick,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    """A standard item opens the date picker; one of the owner's own opens its actions."""
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    value = callback_data.value
    if case is not None and value in documents.checklist(case.purpose):
        current = {d.code: d.submitted_on for d in await repo.list_docs(session, case)}.get(value)
        target = {"target": "std", "code": value}
        await open_picker(
            cq, state, lang, case, clock(), target, documents.doc_name(value), current
        )
        return
    doc_id = parse_doc_id(value)
    doc = await repo.get_custom_doc(session, case, doc_id) if case and doc_id is not None else None
    if doc is None:
        await to_menu(cq, state, lang)
        return
    await state.clear()
    await show(cq, screens.doc_item_view(lang, case.id, doc))


@router.callback_query(Act.filter(F.action == "doc_date"))
async def doc_date(
    cq: CallbackQuery,
    callback_data: Act,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    case, doc = await owned_doc(
        session, cq.from_user.id, callback_data.case_id, callback_data.value
    )
    if doc is None:
        await to_menu(cq, state, lang)
        return
    target = {"target": "custom", "doc_id": doc.id}
    await open_picker(cq, state, lang, case, clock(), target, doc.name, doc.submitted_on)


@router.callback_query(Act.filter(F.action == "doc_del"))
async def doc_del(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    case, doc = await owned_doc(
        session, cq.from_user.id, callback_data.case_id, callback_data.value
    )
    if doc is None:
        await to_menu(cq, state, lang)
        return
    await state.clear()
    await show(cq, screens.confirm_delete_doc(lang, case.id, doc))


@router.callback_query(Act.filter(F.action == "doc_del_yes"))
async def doc_del_yes(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    case, doc = await owned_doc(
        session, cq.from_user.id, callback_data.case_id, callback_data.value
    )
    if doc is None:
        await to_menu(cq, state, lang)
        return
    await repo.delete_custom_doc(session, doc)
    await state.clear()
    await show(cq, await docs_screen(session, lang, case))


# --- naming: add and rename ------------------------------------------------------------


@router.callback_query(Act.filter(F.action == "doc_add"))
async def doc_add(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    if case is None:
        await to_menu(cq, state, lang)
        return
    await state.clear()
    if await repo.count_custom_docs(session, case) >= documents.MAX_CUSTOM:
        notice = "⚠️ " + t(lang, "doc_limit", max=documents.MAX_CUSTOM)
        await show(cq, await docs_screen(session, lang, case, notice))
        return
    await state.set_state(DocName.typing)
    await state.set_data({"case_id": case.id, "doc_id": None})
    await show(cq, screens.doc_name_prompt(lang, case.id))


@router.callback_query(Act.filter(F.action == "doc_ren"))
async def doc_rename(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    case, doc = await owned_doc(
        session, cq.from_user.id, callback_data.case_id, callback_data.value
    )
    if doc is None:
        await to_menu(cq, state, lang)
        return
    await state.set_state(DocName.typing)
    await state.set_data({"case_id": case.id, "doc_id": doc.id})
    await show(cq, screens.doc_name_prompt(lang, case.id, rename=True))


@router.message(DocName.typing, F.text)
async def doc_name_typed(
    msg: Message, session: AsyncSession, state: FSMContext, lang: str, clock: Clock
):
    data = await state.get_data()
    case = await repo.get_case(session, msg.from_user.id, int(data.get("case_id", 0)))
    if case is None:
        await to_menu(msg, state, lang)
        return
    renaming = data.get("doc_id") is not None
    name, error = documents.clean_name(msg.text)
    if error:
        text = t(lang, f"err_{error}", max=documents.MAX_NAME)
        await show(msg, screens.doc_name_prompt(lang, case.id, rename=renaming, error=text))
        return
    if not renaming:
        await open_picker(msg, state, lang, case, clock(), {"target": "new"}, name, None)
        return
    doc = await repo.get_custom_doc(session, case, int(data["doc_id"]))
    if doc is None:
        await to_menu(msg, state, lang)
        return
    await repo.rename_custom_doc(session, doc, name)
    await state.clear()
    await show(msg, await docs_screen(session, lang, case))


@router.message(DocName.typing)
async def doc_name_not_text(msg: Message, state: FSMContext, lang: str):
    data = await state.get_data()
    renaming = data.get("doc_id") is not None
    error = t(lang, "err_doc_text_only")
    await show(msg, screens.doc_name_prompt(lang, int(data.get("case_id", 0)), renaming, error))


# --- date input ------------------------------------------------------------------------


@router.callback_query(DocDate.picking, Month.filter())
async def flip_month(
    cq: CallbackQuery, callback_data: Month, state: FSMContext, lang: str, clock: Clock
):
    await show_picker(cq, state, lang, clock(), month=(callback_data.y, callback_data.m))


@router.callback_query(DocDate.picking, Day.filter())
async def pick_day(
    cq: CallbackQuery,
    callback_data: Day,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    try:
        d = date(callback_data.y, callback_data.m, callback_data.d)
    except ValueError:
        await show_picker(cq, state, lang, clock(), error=t(lang, "err_not_date"))
        return
    await accept_date(cq, d, session, state, lang, clock())


@router.callback_query(DocDate.picking, Act.filter(F.action.in_({"today", "yesterday"})))
async def quick_day(
    cq: CallbackQuery,
    callback_data: Act,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    today = clock()
    d = today if callback_data.action == "today" else today - timedelta(days=1)
    await accept_date(cq, d, session, state, lang, today)


@router.message(DocDate.picking, F.text)
async def typed_date(
    msg: Message, session: AsyncSession, state: FSMContext, lang: str, clock: Clock
):
    today = clock()
    d = parse_date(msg.text, today)
    if d is None:
        await show_picker(msg, state, lang, today, error=t(lang, "err_not_date"))
        return
    await accept_date(msg, d, session, state, lang, today)


async def accept_date(
    event, d: date, s: AsyncSession, state: FSMContext, lang: str, today: date
) -> None:
    data = await state.get_data()
    case = await repo.get_case(s, event.from_user.id, int(data.get("case_id", 0)))
    if case is None:
        await to_menu(event, state, lang)
        return
    filed = case.dates()[Milestone.filed]
    if error := documents.date_error(d, filed, today):
        text = t(
            lang,
            f"err_{error}",
            date=screens.fmt(documents.earliest(filed)),
            days=documents.MARGIN_DAYS,
        )
        await show_picker(event, state, lang, today, error=text)
        return
    notice = None
    target = data.get("target")
    if target == "std":
        await repo.set_standard_doc(s, case, data["code"], d)
    elif target == "custom":
        doc = await repo.get_custom_doc(s, case, int(data["doc_id"]))
        if doc is None:
            await to_menu(event, state, lang)
            return
        await repo.set_doc_date(s, doc, d)
    else:
        try:
            await repo.add_custom_doc(s, case, data["name"], d)
        except repo.TooManyDocs:
            notice = "⚠️ " + t(lang, "doc_limit", max=documents.MAX_CUSTOM)
    await state.clear()
    await show(event, await docs_screen(s, lang, case, notice))


@router.callback_query(DocDate.picking, Act.filter(F.action == "clear_date"))
async def clear_date(cq: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str):
    data = await state.get_data()
    case = await repo.get_case(session, cq.from_user.id, int(data.get("case_id", 0)))
    if case is None:
        await to_menu(cq, state, lang)
        return
    if data.get("target") == "std":
        await repo.set_standard_doc(session, case, data["code"], None)
    elif data.get("target") == "custom":
        doc = await repo.get_custom_doc(session, case, int(data["doc_id"]))
        if doc is not None:
            await repo.set_doc_date(session, doc, None)
    await state.clear()
    await show(cq, await docs_screen(session, lang, case))
