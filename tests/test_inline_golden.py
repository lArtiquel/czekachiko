"""Golden output of inline mode, pinned byte for byte.

The Mini App's «📤 Отправить в чат» posts these cards, so their text, buttons and caching
must not drift. The golden file was captured from the bot before its old UI was removed.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, Update

from czekachiko import documents
from czekachiko.app import build_dispatcher
from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from tests.fakes import _ids, _user, make_bot

GOLDEN = Path(__file__).parent / "golden" / "inline.json"
UID = 548
V, P, C, M = Voivodeship, Purpose, Channel, Milestone

# owner, voivodeship, purpose, then the 2026 dates of each milestone in order: filed,
# case_number, braki, fingerprints, decision, card. Case counts per voivodeship differ
# (9, 2, 1), so the empty query lists them in a fixed order.
SEED = [
    (1, V.mazowieckie, P.jdg, "01-05", "02-02", None, "04-20", "07-01", "08-10"),
    (1, V.mazowieckie, P.jdg, "01-12", None, None, "05-04", "08-03", None),
    (1, V.mazowieckie, P.jdg, "02-02", "03-02", None, "06-15", None, None),
    (1, V.mazowieckie, P.jdg, "02-16", None, None, "07-06", "09-28", None),
    (1, V.mazowieckie, P.jdg, "03-02", None, "04-13", "07-27", None, None),
    (2, V.mazowieckie, P.jdg, "03-23", None, None, "08-31", None, None),
    (3, V.mazowieckie, P.praca, "04-01", None, None, "07-15", None, None),
    (3, V.mazowieckie, P.praca, "05-04", None, None, None, None, None),
    (3, V.malopolskie, P.praca, "02-10", None, None, "05-20", "08-17", None),
    (3, V.malopolskie, P.praca, "03-15", None, None, None, None, None),
    (4, V.dolnoslaskie, P.studia, "06-01", None, None, None, None, None),
    # The querying user's own case, with a ticked document that must never reach a card.
    (UID, V.mazowieckie, P.jdg, "08-03", "09-07", None, None, None, None),
]


def on(day: str) -> date:
    return date.fromisoformat(f"2026-{day}")


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        admin_tg_id=None,
        calendar_url=None,
        throttle=False,
        ephemeral_delay=0,
    )
    async with session_factory() as s:
        for i, (owner, voiv, purpose, filed, *rest) in enumerate(SEED):
            await repo.ensure_user(s, owner)
            case = await repo.create_case(s, owner, voiv, purpose, C.paper, on(filed), f"g{i}")
            for milestone, day in zip(list(M)[1:], rest, strict=True):
                if day is not None:
                    await repo.set_milestone(s, case, milestone, on(day))
            if owner == UID:
                code = documents.checklist(purpose)[0]
                await repo.set_standard_doc(s, case, code, on("08-03"))
                own_id = case.id
        foreign_id = (await repo.list_cases(s, 1))[0].id
        await s.commit()
    return dp, bot, tg, own_id, foreign_id


def snapshot(answer: AnswerInlineQuery) -> dict:
    def markup(kb):
        if kb is None:
            return None
        return [[{"text": b.text, "url": b.url} for b in row] for row in kb.inline_keyboard]

    button = answer.button
    return {
        "cache_time": answer.cache_time,
        "is_personal": answer.is_personal,
        "button": button and {"text": button.text, "start_parameter": button.start_parameter},
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "message_text": r.input_message_content.message_text,
                "parse_mode": r.input_message_content.parse_mode,
                "reply_markup": markup(r.reply_markup),
            }
            for r in answer.results
        ],
    }


QUERIES = {
    "empty": lambda own, foreign: "",
    "alias_warszawa": lambda own, foreign: "варшава",
    "stats_code": lambda own, foreign: "s:jdg:6",
    "compare_code": lambda own, foreign: "s:praca:5,6",
    "own_case": lambda own, foreign: f"c:{own}",
    "foreign_case": lambda own, foreign: f"c:{foreign}",
    "malformed_case": lambda own, foreign: "c:abc",
    "own_case_en": lambda own, foreign: f"c:{own}",
    "compare_code_en": lambda own, foreign: "s:praca:5,6",
}


@pytest.mark.parametrize("name", list(QUERIES))
async def test_inline_output_is_unchanged(env, session_factory, name):
    dp, bot, tg, own_id, foreign_id = env
    query = QUERIES[name](own_id, foreign_id)
    if name.endswith("_en"):
        async with session_factory() as s:
            await repo.set_lang(s, UID, "en")
            await s.commit()
    iq = InlineQuery(id=str(next(_ids)), from_user=_user(UID), query=query, offset="")
    await dp.feed_update(bot, Update(update_id=next(_ids), inline_query=iq))
    (answer,) = [c for c in tg.calls if isinstance(c, AnswerInlineQuery)]
    got = snapshot(answer)
    expected = json.loads(GOLDEN.read_text())[name]
    assert expected.pop("query") == query
    assert got == expected
