from collections.abc import Callable
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.domain import Milestone, Purpose, Voivodeship
from czekachiko.render import show
from czekachiko.stats import WHO_NOW_DAYS, who_now
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Nav, Pick

router = Router(name="stats")


@router.callback_query(Nav.filter(F.to == "stats"))
async def pick_voiv(cq: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await show(cq, screens.stats_pick_voiv(lang))


@router.callback_query(Pick.filter(F.field == "stats_voiv"))
async def pick_purpose(cq: CallbackQuery, callback_data: Pick, lang: str):
    voiv = Voivodeship(callback_data.value)
    await show(cq, screens.stats_pick_purpose(lang, voiv))


@router.callback_query(Pick.filter(F.field == "stats_purpose"))
async def stats_view(
    cq: CallbackQuery,
    callback_data: Pick,
    session: AsyncSession,
    lang: str,
    clock: Callable[[], date],
):
    voiv_s, purpose_s = callback_data.value.split("|", 1)
    voiv, purpose = Voivodeship(voiv_s), Purpose(purpose_s)
    aggs = await repo.chain_aggregates(session, voiv, purpose)
    today = clock()
    since = today - timedelta(days=WHO_NOW_DAYS)
    fp = who_now(
        await repo.recent_events(session, voiv, purpose, Milestone.fingerprints, since), today
    )
    dec = who_now(
        await repo.recent_events(session, voiv, purpose, Milestone.decision, since), today
    )
    await show(cq, screens.stats_view(lang, voiv, purpose, aggs, fp, dec))
