"""Compare voivodeships with checkboxes and post the card to any chat via inline mode."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko import share
from czekachiko.db import repo
from czekachiko.domain import Purpose, Voivodeship
from czekachiko.i18n import label, t, voiv_label
from czekachiko.render import show
from czekachiko.ui.keyboards import (
    Act,
    Nav,
    Pick,
    btn,
    enum_picker,
    grid,
    markup,
    nav_row,
    send_to_chat,
)

router = Router(name="share")
BOT_URL = "https://t.me/czekachiko_bot"
MAX_RESULTS = 20


class Compare(StatesGroup):
    purpose = State()
    voivs = State()


def open_bot_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_open_bot"), url=BOT_URL)]]
    )


async def build_card(s: AsyncSession, lang: str, purpose: str, voivs: list[Voivodeship]) -> str:
    chains = {v: await repo.chain_aggregates(s, v, purpose) for v in voivs}
    return share.card_text(lang, purpose, chains)


# --- compare picker ------------------------------------------------------------


def purpose_picker(lang: str):
    opts = [(str(p), label(lang, "PURPOSE_BUTTONS", p)) for p in Purpose]
    kb = enum_picker(lang, "cmp_purpose", opts, cols=1, back=Nav(to="stats"), cancel=False)
    return t(lang, "cmp_pick_purpose"), kb


def toggles_view(lang: str, purpose: str, selected: list[str]):
    rows = grid(
        [
            btn(
                ("✅ " if v.value in selected else "⬜ ") + voiv_label(v),
                Act(action="cmp_toggle", value=v.value),
            )
            for v in Voivodeship
        ],
        2,
    )
    rows.append([btn(t(lang, "btn_cmp_show", n=len(selected)), Act(action="cmp_show"))])
    rows.append(nav_row(lang, Nav(to="compare")))
    head = t(
        lang,
        "cmp_pick_voivs",
        purpose=label(lang, "PURPOSE_LABELS", Purpose(purpose)),
        max=share.MAX_COMPARE,
    )
    return head, markup(rows)


async def start_compare(event, state: FSMContext, lang: str) -> None:
    await state.clear()
    await state.set_state(Compare.purpose)
    await show(event, purpose_picker(lang))


@router.message(CommandStart(deep_link=True, magic=F.args == "pick"))
async def deep_link_pick(msg: Message, state: FSMContext, lang: str):
    await start_compare(msg, state, lang)


@router.callback_query(Nav.filter(F.to == "compare"))
async def compare(cq: CallbackQuery, state: FSMContext, lang: str):
    await start_compare(cq, state, lang)


@router.callback_query(Pick.filter(F.field == "cmp_purpose"))
async def compare_purpose(cq: CallbackQuery, callback_data: Pick, state: FSMContext, lang: str):
    purpose = Purpose(callback_data.value).value
    await state.set_state(Compare.voivs)
    await state.update_data(cmp_purpose=purpose, cmp=[])
    await show(cq, toggles_view(lang, purpose, []))


@router.callback_query(Compare.voivs, Act.filter(F.action == "cmp_toggle"))
async def compare_toggle(cq: CallbackQuery, callback_data: Act, state: FSMContext, lang: str):
    voiv = Voivodeship(callback_data.value).value
    data = await state.get_data()
    selected = list(data.get("cmp", []))
    if voiv in selected:
        selected.remove(voiv)
    elif len(selected) >= share.MAX_COMPARE:
        await cq.answer(t(lang, "cmp_limit", max=share.MAX_COMPARE))
        return
    else:
        selected.append(voiv)
    await state.update_data(cmp=selected)
    await show(cq, toggles_view(lang, data["cmp_purpose"], selected))


@router.callback_query(Compare.voivs, Act.filter(F.action.in_({"cmp_show", "cmp_edit"})))
async def compare_show(
    cq: CallbackQuery, callback_data: Act, session: AsyncSession, state: FSMContext, lang: str
):
    data = await state.get_data()
    purpose, selected = data["cmp_purpose"], list(data.get("cmp", []))
    if callback_data.action == "cmp_edit":
        await show(cq, toggles_view(lang, purpose, selected))
        return
    if not selected:
        await cq.answer(t(lang, "cmp_none"))
        return
    voivs = [Voivodeship(v) for v in selected]
    text = await build_card(session, lang, purpose, voivs)
    send = send_to_chat(lang, share.encode(purpose, voivs))
    rows = [[send], [btn(t(lang, "btn_cmp_edit"), Act(action="cmp_edit"))], nav_row(lang)]
    await show(cq, (text, markup(rows)))


# --- inline mode -------------------------------------------------------------------


def article(lang: str, purpose: str, voivs: list[Voivodeship], text: str):
    names = ", ".join(voiv_label(v) for v in voivs)
    return InlineQueryResultArticle(
        id=share.encode(purpose, voivs),
        title=f"{names} · {label(lang, 'PURPOSE_LABELS', Purpose(purpose))}",
        description=t(lang, "card_description"),
        input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
        reply_markup=open_bot_kb(lang),
    )


async def case_article(s: AsyncSession, iq: InlineQuery, lang: str, today) -> list:
    from czekachiko.handlers.cases import case_screen

    try:
        case_id = int(iq.query.strip()[2:])
    except ValueError:
        return []
    case = await repo.get_case(s, iq.from_user.id, case_id)  # only the owner can share it
    if case is None:
        return []
    text, _ = await case_screen(s, lang, case, today)
    text = f"{t(lang, 'case_card_title')}\n\n{text}\n\n<i>{t(lang, 'card_footer')}</i>"
    title = f"{t(lang, 'case_card_label')} · {voiv_label(case.voivodeship)} · " + label(
        lang, "PURPOSE_LABELS", Purpose(case.purpose)
    )
    return [
        InlineQueryResultArticle(
            id=f"c:{case.id}",
            title=title,
            description=t(lang, "card_description"),
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
            reply_markup=open_bot_kb(lang),
        )
    ]


@router.inline_query(F.query.startswith("c:"))
async def inline_case(iq: InlineQuery, session: AsyncSession, lang: str, clock):
    results = await case_article(session, iq, lang, clock())
    await iq.answer(results, cache_time=0, is_personal=True)


@router.inline_query()
async def inline(iq: InlineQuery, session: AsyncSession, lang: str, webapp_url: str):
    query = iq.query.strip()
    combos: list[tuple[str, list[Voivodeship]]] = []
    if (decoded := share.decode(query)) is not None:
        combos = [decoded]
    else:
        voivs = share.match_voivodeships(query) if query else []
        if not voivs:
            voivs = [Voivodeship(v) for v, _ in await repo.admin_counts(session)] or list(
                Voivodeship
            )
        purposes = share.match_purposes(query) or list(Purpose)
        for v in voivs:
            with_data = [
                p for p in purposes if any((await repo.chain_aggregates(session, v, p)).values())
            ]
            for p in with_data or purposes[:1]:
                combos.append((p.value, [v]))
    results = []
    for purpose, voivs in combos[:MAX_RESULTS]:
        results.append(
            article(lang, purpose, voivs, await build_card(session, lang, purpose, voivs))
        )
    # Above the results: opens the app's stats, which can return here via switchInlineQuery.
    button = InlineQueryResultsButton(
        text=t(lang, "inline_open_app"), web_app=WebAppInfo(url=webapp_url + "#/stats")
    )
    await iq.answer(results, cache_time=30, is_personal=False, button=button)
