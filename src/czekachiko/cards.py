"""Text of the inline-mode cards: stats, comparisons and the owner's case. Pure.

Cards are parsed as HTML and posted to other chats, so they carry no free text: no
document names, nothing from feedback.
"""

from collections.abc import Iterable
from datetime import date

from czekachiko.db.models import Case
from czekachiko.domain import (
    CHAIN,
    PERMIT_TYPE,
    Channel,
    Milestone,
    Purpose,
    Voivodeship,
    canonical,
    group_of,
)
from czekachiko.i18n import label, t, voiv_label
from czekachiko.stats import Aggregate, Forecast

M = Milestone
Chain = dict[tuple[Milestone, Milestone], Aggregate | None]


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def selection_label(lang: str, purposes: Iterable[Purpose | str]) -> str:
    """One purpose by its label, a whole permit type as "<type>, all bases", else a list."""
    chosen = canonical(purposes)
    if len(chosen) == 1:
        return label(lang, "PURPOSE_LABELS", chosen[0])
    group = group_of(chosen)
    if group is not None:
        return t(lang, "all_bases", group=label(lang, "PERMIT_TYPE_LABELS", group))
    return ", ".join(label(lang, "PURPOSE_LABELS", p) for p in chosen)


def place_label(lang: str, voiv: Voivodeship | str | None) -> str:
    return voiv_label(voiv) if voiv is not None else t(lang, "all_poland")


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
        group = label(lang, "PERMIT_TYPE_LABELS", PERMIT_TYPE[Purpose(case.purpose)])
        scope = t(
            lang,
            f"fc_scope_{f.scope}",
            voiv=voiv_label(case.voivodeship),
            purpose=purpose,
            group=group,
        )
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


def stats_card(
    lang: str, purpose: str | Iterable[str], chains: dict[Voivodeship | None, Chain]
) -> str:
    """One place's chain, or several side by side for a comparison.

    `purpose` is one purpose or several; a `None` place is all of Poland.
    """
    purposes = [purpose] if isinstance(purpose, str) else list(purpose)
    title = t(lang, "card_title", purpose=selection_label(lang, purposes))
    parts = [title]
    for v, chain in chains.items():
        parts.append(f"<b>{place_label(lang, v)}</b>\n" + "\n".join(chain_lines(lang, chain)))
    parts.append(f"<i>{t(lang, 'card_footer')}</i>")
    return "\n\n".join(parts)
