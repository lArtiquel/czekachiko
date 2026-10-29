"""Text of the inline-mode cards: stats, comparisons and the owner's case. Pure.

Cards are parsed as HTML and posted to other chats, so they carry no free text: no
document names, nothing from feedback.
"""

from datetime import date

from czekachiko.db.models import Case
from czekachiko.domain import CHAIN, Channel, Milestone, Purpose, Voivodeship
from czekachiko.i18n import label, t, voiv_label
from czekachiko.stats import Aggregate, Forecast

M = Milestone
Chain = dict[tuple[Milestone, Milestone], Aggregate | None]


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def case_title(lang: str, case: Case) -> str:
    return (
        f"{voiv_label(case.voivodeship)} · {label(lang, 'PURPOSE_LABELS', Purpose(case.purpose))}"
    )


def chain_lines(lang: str, chain: Chain, dates: dict | None = None) -> list[str]:
    """Each milestone from filing: the case's own date (if any) and the typical span."""
    lines = []
    filed = (dates or {}).get(M.filed)
    for a, b in CHAIN:
        name = label(lang, "MILESTONE_LABELS", b)
        if dates is None:
            head = f"• {name}"
        elif b in dates:
            own = t(lang, "chain_own", days=(dates[b] - filed).days) if filed else ""
            head = f"✅ {name} — {fmt(dates[b])} · {own}"
        else:
            head = f"⏳ {name}"
        agg = chain.get((a, b))
        typical = (
            t(lang, "chain_line", mean=round(agg.mean), min=agg.min, max=agg.max, n=agg.n)
            if agg is not None
            else t(lang, "chain_none")
        )
        lines.append(f"{head}\n    <i>{typical}</i>")
    return lines


def forecast_text(lang: str, case: Case, f: Forecast | None) -> str:
    if f is None:
        return t(lang, "fc_all_done")
    target = label(lang, "MILESTONE_LABELS", f.target)
    head = t(lang, "fc_title", target=target)
    if f.kind == "no_data":
        return f"{head}\n{t(lang, 'fc_no_data')}"
    purpose = label(lang, "PURPOSE_LABELS", Purpose(case.purpose))
    if f.kind == "waited_longer":
        body = t(lang, "fc_waited_longer", x=f.waited_longer_than, y=f.total)
    else:
        scope = t(lang, f"fc_scope_{f.scope}", voiv=voiv_label(case.voivodeship), purpose=purpose)
        body = t(
            lang,
            "fc_window",
            start=fmt(f.start),
            end=fmt(f.end),
            likely=fmt(f.likely),
            n=f.n,
            scope=scope,
        )
    extra = t(lang, "fc_fastest_slowest", fastest=f.fastest, slowest=f.slowest)
    return f"{head}\n{body}\n<i>{extra}</i>"


def case_card(lang: str, case: Case, f: Forecast | None, chain: Chain) -> str:
    """The owner's case: milestone chain with own dates, the forecast and the disclaimer."""
    dates = case.dates()
    channel = label(lang, "CHANNEL_LABELS", Channel(case.channel))
    lines = [
        t(lang, "case_card_title"),
        "",
        f"<b>{case_title(lang, case)}</b> · {channel}",
        f"📨 {label(lang, 'MILESTONE_LABELS', M.filed)} — {fmt(dates[M.filed])}",
        "",
        *chain_lines(lang, chain, dates),
        "",
        forecast_text(lang, case, f),
        "",
        t(lang, "disclaimer"),
        "",
        f"<i>{t(lang, 'card_footer')}</i>",
    ]
    return "\n".join(lines)


def stats_card(lang: str, purpose: str, chains: dict[Voivodeship, Chain]) -> str:
    """One voivodeship's chain, or several side by side for a comparison."""
    title = t(lang, "card_title", purpose=label(lang, "PURPOSE_LABELS", Purpose(purpose)))
    parts = [title]
    for v, chain in chains.items():
        parts.append(f"<b>{voiv_label(v)}</b>\n" + "\n".join(chain_lines(lang, chain)))
    parts.append(f"<i>{t(lang, 'card_footer')}</i>")
    return "\n\n".join(parts)
