"""Add-case wizard, case view, marking milestones, outlier confirmation, deletion."""

import uuid
from collections.abc import Callable
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.dates import parse_date, validate_milestones
from czekachiko.db import repo
from czekachiko.db.models import Case
from czekachiko.domain import INTERVAL_PAIRS, Channel, Milestone, Purpose, Voivodeship
from czekachiko.i18n import t
from czekachiko.render import show
from czekachiko.stats import Forecast, aggregate, forecast, is_suspicious
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Act, Day, Month, Nav, Pick, date_picker

router = Router(name="cases")
M = Milestone
Clock = Callable[[], date]


class AddCase(StatesGroup):
    voiv = State()
    purpose = State()
    channel = State()
    filed = State()
    more = State()


class MarkDate(StatesGroup):
    picking = State()
    confirm_outlier = State()


# --- helpers ---------------------------------------------------------------


async def case_forecast(s: AsyncSession, case: Case, today: date) -> Forecast | None:
    values: dict[tuple[str, M, M], list[int]] = {}
    for scope in ("voiv", "national"):
        for a, b in INTERVAL_PAIRS:
            values[(scope, a, b)] = await repo.interval_values(
                s, scope, case.voivodeship, case.purpose, a, b
            )
    return forecast(case.dates(), today, lambda sc, a, b: values.get((sc, a, b), []))


async def case_screen(s: AsyncSession, lang: str, case: Case, today: date):
    chain = await repo.chain_aggregates(s, case.voivodeship, case.purpose)
    return screens.case_view(lang, case, await case_forecast(s, case, today), chain)


async def show_case(event, s: AsyncSession, state: FSMContext, lang: str, case: Case, today: date):
    await state.clear()
    await show(event, await case_screen(s, lang, case, today))


async def show_date_picker(
    event,
    state: FSMContext,
    lang: str,
    today: date,
    error: str | None = None,
    new: bool = False,
    month: tuple[int, int] | None = None,
) -> None:
    data = await state.get_data()
    milestone = M(data.get("milestone", M.filed))
    y, m = month or (data.get("pick_y", today.year), data.get("pick_m", today.month))
    await state.update_data(pick_y=y, pick_m=m)
    text = screens.date_prompt(lang, milestone)
    if milestone == M.filed and await state.get_state() == AddCase.filed.state:
        text = t(lang, "ask_filed")
    if error:
        text = f"⚠️ {error}\n\n{text}"
    can_clear = bool(data.get("can_clear"))
    await show(event, (text, date_picker(lang, y, m, today, can_clear=can_clear)), new=new)


# --- wizard ----------------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "add"))
async def start_add(
    event: CallbackQuery | Message, session: AsyncSession, state: FSMContext, lang: str
):
    if await repo.count_cases(session, event.from_user.id) >= repo.MAX_CASES:
        await show(event, (t(lang, "case_limit"), screens.main_menu(lang)[1]))
        return
    await state.clear()
    await state.set_state(AddCase.voiv)
    await state.update_data(client_token=uuid.uuid4().hex)
    await show(event, screens.wizard_prompt(lang, "voiv"))


@router.callback_query(AddCase.voiv, Pick.filter(F.field == "voiv"))
async def pick_voiv(cq: CallbackQuery, callback_data: Pick, state: FSMContext, lang: str):
    Voivodeship(callback_data.value)
    await state.update_data(voiv=callback_data.value)
    await state.set_state(AddCase.purpose)
    await show(cq, screens.wizard_prompt(lang, "purpose"))


@router.callback_query(AddCase.purpose, Pick.filter(F.field == "purpose"))
async def pick_purpose(cq: CallbackQuery, callback_data: Pick, state: FSMContext, lang: str):
    Purpose(callback_data.value)
    await state.update_data(purpose=callback_data.value)
    await state.set_state(AddCase.channel)
    await show(cq, screens.wizard_prompt(lang, "channel"))


@router.callback_query(AddCase.channel, Pick.filter(F.field == "channel"))
async def pick_channel(
    cq: CallbackQuery, callback_data: Pick, state: FSMContext, lang: str, clock: Clock
):
    Channel(callback_data.value)
    await state.update_data(channel=callback_data.value, milestone=M.filed.value, can_clear=False)
    await state.set_state(AddCase.filed)
    await show_date_picker(cq, state, lang, clock())


@router.callback_query(Pick.filter(F.field == "milestone"))
async def pick_milestone(
    cq: CallbackQuery,
    callback_data: Pick,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    if case is None:
        await show(cq, screens.main_menu(lang))
        await state.clear()
        return
    milestone = M(callback_data.value)
    return_to = "more" if await state.get_state() == AddCase.more.state else "case"
    existing = case.dates().get(milestone)
    anchor = existing or clock()
    await state.set_state(MarkDate.picking)
    await state.update_data(
        case_id=case.id,
        milestone=milestone.value,
        return_to=return_to,
        can_clear=existing is not None and milestone != M.filed,
        pick_y=anchor.year,
        pick_m=anchor.month,
    )
    await show_date_picker(cq, state, lang, clock())


# --- date input --------------------------------------------------------------


@router.callback_query(AddCase.filed, Month.filter())
@router.callback_query(MarkDate.picking, Month.filter())
async def flip_month(
    cq: CallbackQuery, callback_data: Month, state: FSMContext, lang: str, clock: Clock
):
    await show_date_picker(cq, state, lang, clock(), month=(callback_data.y, callback_data.m))


@router.callback_query(AddCase.filed, Day.filter())
@router.callback_query(MarkDate.picking, Day.filter())
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
        await show_date_picker(cq, state, lang, clock(), error=t(lang, "err_not_date"))
        return
    await accept_date(cq, d, session, state, lang, clock())


@router.callback_query(AddCase.filed, Act.filter(F.action.in_({"today", "yesterday"})))
@router.callback_query(MarkDate.picking, Act.filter(F.action.in_({"today", "yesterday"})))
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


@router.message(AddCase.filed, F.text)
@router.message(MarkDate.picking, F.text)
async def typed_date(
    msg: Message, session: AsyncSession, state: FSMContext, lang: str, clock: Clock
):
    today = clock()
    d = parse_date(msg.text, today)
    if d is None:
        await show_date_picker(msg, state, lang, today, error=t(lang, "err_not_date"), new=True)
        return
    await accept_date(msg, d, session, state, lang, today)


async def accept_date(
    event, d: date, s: AsyncSession, state: FSMContext, lang: str, today: date
) -> None:
    current = await state.get_state()
    data = await state.get_data()
    new = isinstance(event, Message)

    if current == AddCase.filed.state:
        errors = validate_milestones({M.filed: d}, today)
        if errors:
            await show_date_picker(
                event, state, lang, today, error=t(lang, f"err_{errors[0]}"), new=new
            )
            return
        user_id = event.from_user.id
        try:
            case = await repo.create_case(
                s,
                user_id,
                Voivodeship(data["voiv"]),
                Purpose(data["purpose"]),
                Channel(data["channel"]),
                d,
                data["client_token"],
            )
        except repo.TooManyCases:
            await state.clear()
            await show(event, (t(lang, "case_limit"), screens.main_menu(lang)[1]), new=new)
            return
        await state.set_state(AddCase.more)
        await state.update_data(case_id=case.id)
        await show(event, screens.wizard_more(lang, case), new=new)
        return

    case = await repo.get_case(s, event.from_user.id, int(data.get("case_id", 0)))
    if case is None:
        await state.clear()
        await show(event, screens.main_menu(lang), new=new)
        return
    milestone = M(data["milestone"])
    dates = {M(k): v for k, v in case.dates().items()} | {milestone: d}
    errors = validate_milestones(dates, today)
    if errors:
        await show_date_picker(
            event, state, lang, today, error=t(lang, f"err_{errors[0]}"), new=new
        )
        return
    suspicious = await find_outlier(s, case, dates, milestone)
    if suspicious is not None:
        a, b, value, typical = suspicious
        await state.set_state(MarkDate.confirm_outlier)
        await state.update_data(pending=d.isoformat())
        await show(
            event,
            screens.outlier_prompt(lang, case.id, case.voivodeship, a, b, typical, value),
            new=new,
        )
        return
    await save_and_return(event, s, state, lang, case, milestone, d, False, today)


async def find_outlier(s: AsyncSession, case: Case, dates: dict[M, date], milestone: M):
    for a, b in INTERVAL_PAIRS:
        if milestone not in (a, b) or a not in dates or b not in dates:
            continue
        value = (dates[b] - dates[a]).days
        values = await repo.interval_values(s, "voiv", case.voivodeship, case.purpose, a, b)
        if is_suspicious(value, values):
            return a, b, value, aggregate(values)
    return None


async def save_and_return(
    event,
    s: AsyncSession,
    state: FSMContext,
    lang: str,
    case: Case,
    milestone: M,
    d: date,
    confirmed: bool,
    today: date,
) -> None:
    data = await state.get_data()
    await repo.set_milestone(s, case, milestone, d, confirmed_outlier=confirmed)
    new = isinstance(event, Message)
    if data.get("return_to") == "more":
        await state.set_state(AddCase.more)
        await show(event, screens.wizard_more(lang, case), new=new)
        return
    await state.clear()
    await show(event, await case_screen(s, lang, case, today), new=new)


@router.callback_query(MarkDate.picking, Act.filter(F.action == "clear_date"))
async def clear_date(
    cq: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str, clock: Clock
):
    data = await state.get_data()
    case = await repo.get_case(session, cq.from_user.id, int(data.get("case_id", 0)))
    milestone = M(data.get("milestone", M.filed))
    if case is None or milestone == M.filed:
        await state.clear()
        await show(cq, screens.main_menu(lang))
        return
    await repo.clear_milestone(session, case, milestone)
    await show_case(cq, session, state, lang, case, clock())


@router.callback_query(MarkDate.confirm_outlier, Act.filter(F.action == "outlier_ok"))
async def outlier_ok(
    cq: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str, clock: Clock
):
    data = await state.get_data()
    case = await repo.get_case(session, cq.from_user.id, int(data.get("case_id", 0)))
    if case is None or "pending" not in data:
        await state.clear()
        await show(cq, screens.main_menu(lang))
        return
    d = date.fromisoformat(data["pending"])
    await save_and_return(cq, session, state, lang, case, M(data["milestone"]), d, True, clock())


@router.callback_query(MarkDate.confirm_outlier, Act.filter(F.action == "outlier_fix"))
async def outlier_fix(cq: CallbackQuery, state: FSMContext, lang: str, clock: Clock):
    await state.set_state(MarkDate.picking)
    await show_date_picker(cq, state, lang, clock())


# --- case screens -------------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "cases"))
async def cases_list(cq: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str):
    await state.clear()
    await show(cq, screens.cases_list(lang, await repo.list_cases(session, cq.from_user.id)))


@router.callback_query(Nav.filter(F.to == "case"))
async def case_view(
    cq: CallbackQuery,
    callback_data: Nav,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    clock: Clock,
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    if case is None:
        await state.clear()
        await show(cq, screens.main_menu(lang))
        return
    await show_case(cq, session, state, lang, case, clock())


@router.callback_query(Nav.filter(F.to == "mark"))
async def mark(
    cq: CallbackQuery, callback_data: Nav, session: AsyncSession, state: FSMContext, lang: str
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    await state.clear()
    await show(cq, screens.milestone_picker(lang, case) if case else screens.main_menu(lang))


@router.callback_query(Act.filter(F.action == "del_case"))
async def del_case(cq: CallbackQuery, callback_data: Act, session: AsyncSession, lang: str):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    await show(cq, screens.confirm_delete_case(lang, case.id) if case else screens.main_menu(lang))


@router.callback_query(Act.filter(F.action == "del_case_yes"))
async def del_case_yes(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    case = await repo.get_case(session, cq.from_user.id, callback_data.case_id)
    if case is not None:
        await repo.delete_case(session, case)
    await state.clear()
    await show(cq, screens.cases_list(lang, await repo.list_cases(session, cq.from_user.id)))
