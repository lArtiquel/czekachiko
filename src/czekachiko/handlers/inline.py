"""Inline mode: stats, comparison and case cards for any chat.

The Mini App's «📤 Отправить в чат» opens Telegram's chat picker with one of these queries:
`s:<purpose>:<voivodeship indexes>` (share.encode) or `c:<case id>` (owner only).
"""

from datetime import date

from aiogram import F, Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko import cards, share
from czekachiko.db import repo
from czekachiko.domain import Purpose, Voivodeship
from czekachiko.forecasting import case_forecast
from czekachiko.i18n import label, t, voiv_label
from czekachiko.keyboards import open_bot

router = Router(name="inline")
MAX_RESULTS = 20


async def stats_card(s: AsyncSession, lang: str, purpose: str, voivs: list[Voivodeship]) -> str:
    chains = {v: await repo.chain_aggregates(s, v, purpose) for v in voivs}
    return cards.stats_card(lang, purpose, chains)


def article(lang: str, purpose: str, voivs: list[Voivodeship], text: str):
    names = ", ".join(voiv_label(v) for v in voivs)
    return InlineQueryResultArticle(
        id=share.encode(purpose, voivs),
        title=f"{names} · {label(lang, 'PURPOSE_LABELS', Purpose(purpose))}",
        description=t(lang, "card_description"),
        input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
        reply_markup=open_bot(lang),
    )


async def case_article(s: AsyncSession, iq: InlineQuery, lang: str, today: date) -> list:
    try:
        case_id = int(iq.query.strip()[2:])
    except ValueError:
        return []
    case = await repo.get_case(s, iq.from_user.id, case_id)  # only the owner can share it
    if case is None:
        return []
    chain = await repo.chain_aggregates(s, case.voivodeship, case.purpose)
    text = cards.case_card(lang, case, await case_forecast(s, case, today), chain)
    title = f"{t(lang, 'case_card_label')} · {voiv_label(case.voivodeship)} · " + label(
        lang, "PURPOSE_LABELS", Purpose(case.purpose)
    )
    return [
        InlineQueryResultArticle(
            id=f"c:{case.id}",
            title=title,
            description=t(lang, "card_description"),
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
            reply_markup=open_bot(lang),
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
            article(lang, purpose, voivs, await stats_card(session, lang, purpose, voivs))
        )
    # Above the results: opens the app's stats, which can return here via switchInlineQuery.
    button = InlineQueryResultsButton(
        text=t(lang, "inline_open_app"), web_app=WebAppInfo(url=webapp_url + "#/stats")
    )
    await iq.answer(results, cache_time=30, is_personal=False, button=button)
