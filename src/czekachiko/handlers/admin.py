from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import t, voiv_label
from czekachiko.render import show
from czekachiko.ui import screens

router = Router(name="admin")


@router.message(Command("admin"))
async def admin(
    msg: Message, command: CommandObject, session: AsyncSession, lang: str, admin_tg_id: int | None
):
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        await show(msg, screens.main_menu(lang))
        return
    if (command.args or "").strip() == "recompute":
        await repo.recompute_all(session)
        await msg.answer(t(lang, "admin_recomputed"))
        return
    counts = await repo.admin_counts(session)
    recent = await repo.admin_recent(session)
    lines = [t(lang, "admin_title"), ""]
    lines += [f"{voiv_label(v)}: {n}" for v, n in counts] or ["—"]
    lines.append("")
    for c in recent:
        filed = c.dates().get("filed")
        lines.append(
            f"#{c.id} {voiv_label(c.voivodeship)} · {c.purpose} · {filed:%m.%Y}"
            if filed
            else f"#{c.id}"
        )
    await msg.answer("\n".join(lines))
