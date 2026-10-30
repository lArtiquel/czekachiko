from aiogram import Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import t, voiv_label

router = Router(name="admin")


@router.message(Command("admin"))
async def admin(
    msg: Message, command: CommandObject, session: AsyncSession, lang: str, admin_tg_id: int | None
):
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        raise SkipHandler  # everyone else gets the usual fallback
    if (command.args or "").strip() == "recompute":
        await repo.recompute_all(session)
        await msg.answer(t(lang, "admin_recomputed"))
        return
    counts = await repo.admin_counts(session)
    recent = await repo.admin_recent(session)
    lines = [t(lang, "admin_title"), ""]
    lines += [f"{voiv_label(v)}: {n}" for v, n in counts] or ["—"]
    lines += ["", *(f"{source}: {n}" for source, n in await repo.source_counts(session))]
    lines.append("")
    for c in recent:
        filed = c.dates().get("filed")
        lines.append(
            f"#{c.id} {voiv_label(c.voivodeship)} · {c.purpose} · {filed:%m.%Y}"
            if filed
            else f"#{c.id}"
        )
    await msg.answer("\n".join(lines))


@router.message(Command("history"))
async def history(
    msg: Message, command: CommandObject, session: AsyncSession, admin_tg_id: int | None
):
    """`/history <user id>`: the support thread with one user, for the maintainer only."""
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        raise SkipHandler
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await msg.answer("/history <user id>", parse_mode=None)
        return
    rows = await repo.feedback_history(session, int(arg))
    if not rows:
        await msg.answer(t("ru", "history_empty"), parse_mode=None)
        return
    lines = []
    for r in rows:
        arrow = "←" if r.direction == "in" else "→"
        media = f"[{r.media}] " if r.media else ""
        lines.append(f"{arrow} {r.created_at:%d.%m %H:%M} UTC · {media}{r.text}")
    await msg.answer("\n\n".join(lines)[-4000:], parse_mode=None)
