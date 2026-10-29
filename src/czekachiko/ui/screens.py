"""Pure screen renderers: data in, (text, keyboard) out."""

from datetime import date
from urllib.parse import urlencode

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from czekachiko.domain import INTERVAL_PAIRS, Channel, Milestone, Purpose, Voivodeship
from czekachiko.i18n import label, loc, t, voiv_label
from czekachiko.stats import MIN_WINDOW_N, Aggregate, Forecast
from czekachiko.ui.keyboards import Act, Nav, Pick, btn, enum_picker, markup, nav_row

Screen = tuple[str, InlineKeyboardMarkup]
BOT_URL = "https://t.me/czekachiko_bot"
M = Milestone


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def month_span(lang: str, span: tuple[date, date]) -> str:
    months = loc(lang).MONTHS
    a, b = span
    fa, fb = f"{months[a.month - 1].lower()} {a.year}", f"{months[b.month - 1].lower()} {b.year}"
    return fa if a == b else f"{fa} – {fb}"


def case_title(lang: str, case) -> str:
    return (
        f"{voiv_label(case.voivodeship)} · {label(lang, 'PURPOSE_LABELS', Purpose(case.purpose))}"
    )


# --- top level -----------------------------------------------------------


def main_menu(lang: str) -> Screen:
    rows = [
        [btn(t(lang, "btn_add"), Nav(to="add")), btn(t(lang, "btn_cases"), Nav(to="cases"))],
        [
            btn(t(lang, "btn_stats"), Nav(to="stats")),
            btn(t(lang, "btn_calendar"), Nav(to="calendar")),
        ],
        [
            btn(t(lang, "btn_settings"), Nav(to="settings")),
            btn(t(lang, "btn_help"), Nav(to="help")),
        ],
        [InlineKeyboardButton(text=t(lang, "btn_share"), url=share_url(lang))],
    ]
    return t(lang, "menu_title"), markup(rows)


def share_url(lang: str) -> str:
    """Telegram's native "forward to a chat" picker, pre-filled with the bot link."""
    return "https://t.me/share/url?" + urlencode({"url": BOT_URL, "text": t(lang, "share_text")})


def privacy(lang: str) -> Screen:
    return t(lang, "privacy"), markup([nav_row(lang)])


def share_view(lang: str) -> Screen:
    rows = [[InlineKeyboardButton(text=t(lang, "btn_share"), url=share_url(lang))], nav_row(lang)]
    return t(lang, "share_prompt"), markup(rows)


def start_text(lang: str) -> str:
    return f"{t(lang, 'menu_title')}\n\n{t(lang, 'privacy')}"


def help_view(lang: str) -> Screen:
    text = t(lang, "help") + "\n\n" + t(lang, "privacy")
    return text, markup([nav_row(lang)])


# --- cases ---------------------------------------------------------------


def cases_list(lang: str, cases: list) -> Screen:
    rows: list[list[InlineKeyboardButton]] = []
    for c in cases:
        filed = c.dates()[M.filed]
        rows.append([btn(f"{case_title(lang, c)} · {fmt(filed)}", Nav(to="case", case_id=c.id))])
    rows.append([btn(t(lang, "btn_add"), Nav(to="add"))])
    rows.append(nav_row(lang))
    text = t(lang, "cases_title") + "\n\n" + ("" if cases else t(lang, "cases_empty"))
    return text.strip(), markup(rows)


def _forecast_text(lang: str, case, f: Forecast | None) -> str:
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


def case_view(lang: str, case, f: Forecast | None) -> Screen:
    dates = case.dates()
    channel = label(lang, "CHANNEL_LABELS", Channel(case.channel))
    lines = [f"<b>{case_title(lang, case)}</b> · {channel}", ""]
    for m in M:
        if m in dates:
            lines.append(f"✅ {label(lang, 'MILESTONE_LABELS', m)} — {fmt(dates[m])}")
        elif m in (M.fingerprints, M.decision, M.card):
            lines.append(f"⏳ {label(lang, 'MILESTONE_LABELS', m)}")
    lines += ["", _forecast_text(lang, case, f), "", t(lang, "disclaimer")]
    rows = [
        [btn(t(lang, "btn_mark"), Nav(to="mark", case_id=case.id))],
        [btn(t(lang, "btn_delete_case"), Act(action="del_case", case_id=case.id))],
        nav_row(lang, Nav(to="cases")),
    ]
    return "\n".join(lines), markup(rows)


def milestone_picker(lang: str, case) -> Screen:
    dates = case.dates()
    opts = []
    for m in M:
        mark = f" ({fmt(dates[m])})" if m in dates else ""
        opts.append((str(m), f"{label(lang, 'MILESTONE_LABELS', m)}{mark}"))
    kb = enum_picker(
        lang,
        "milestone",
        opts,
        cols=2,
        case_id=case.id,
        back=Nav(to="case", case_id=case.id),
        cancel=False,
    )
    return t(lang, "pick_milestone"), kb


def wizard_more(lang: str, case) -> Screen:
    """After the case is created: pick milestones to add, or Done."""
    dates = case.dates()
    opts = [
        (
            str(m),
            f"{label(lang, 'MILESTONE_LABELS', m)}"
            + (f" ✅ {fmt(dates[m])}" if m in dates else ""),
        )
        for m in M
        if m != M.filed
    ]
    rows = [[btn(lbl, Pick(field="milestone", value=v, case_id=case.id))] for v, lbl in opts]
    rows.append([btn(t(lang, "btn_done"), Nav(to="case", case_id=case.id))])
    rows.append(nav_row(lang))
    return t(lang, "ask_more"), markup(rows)


def confirm_delete_case(lang: str, case_id: int) -> Screen:
    rows = [
        [
            btn(t(lang, "btn_yes_delete"), Act(action="del_case_yes", case_id=case_id)),
            btn(t(lang, "btn_no"), Nav(to="case", case_id=case_id)),
        ],
        nav_row(lang),
    ]
    return t(lang, "confirm_delete_case"), markup(rows)


def outlier_prompt(
    lang: str,
    case_id: int,
    voiv: str,
    from_m: Milestone,
    to_m: Milestone,
    typical: Aggregate,
    value: int,
) -> Screen:
    text = t(
        lang,
        "outlier",
        voiv=voiv_label(voiv),
        from_=label(lang, "MILESTONE_LABELS", from_m),
        to=label(lang, "MILESTONE_LABELS", to_m),
        p10=round(typical.p10),
        p90=round(typical.p90),
        value=value,
    )
    rows = [
        [
            btn(t(lang, "btn_outlier_ok"), Act(action="outlier_ok", case_id=case_id)),
            btn(t(lang, "btn_outlier_fix"), Act(action="outlier_fix", case_id=case_id)),
        ],
        nav_row(lang),
    ]
    return text, markup(rows)


# --- stats ---------------------------------------------------------------


def stats_pick_voiv(lang: str) -> Screen:
    opts = [(str(v), voiv_label(v)) for v in Voivodeship]
    return t(lang, "stats_pick_voiv"), enum_picker(lang, "stats_voiv", opts, cols=2, cancel=False)


def stats_pick_purpose(lang: str, voiv: str) -> Screen:
    opts = [(f"{voiv}|{p}", label(lang, "PURPOSE_BUTTONS", p)) for p in Purpose]
    kb = enum_picker(lang, "stats_purpose", opts, cols=1, back=Nav(to="stats"), cancel=False)
    return t(lang, "stats_pick_purpose"), kb


def stats_view(
    lang: str,
    voiv: str,
    purpose: str,
    aggregates: dict[tuple[Milestone, Milestone], Aggregate | None],
    who_fp: tuple[date, date] | None,
    who_dec: tuple[date, date] | None,
) -> Screen:
    title = t(
        lang,
        "stats_title",
        voiv=voiv_label(voiv),
        purpose=label(lang, "PURPOSE_LABELS", Purpose(purpose)),
    )
    lines = [title, ""]
    for a, b in INTERVAL_PAIRS:
        agg = aggregates.get((a, b))
        if agg is None:
            continue
        names = dict(
            from_=label(lang, "MILESTONE_LABELS", a), to=label(lang, "MILESTONE_LABELS", b)
        )
        if agg.n >= MIN_WINDOW_N:
            lines.append(
                t(
                    lang,
                    "stats_row",
                    p10=round(agg.p10),
                    p90=round(agg.p90),
                    median=round(agg.median),
                    n=agg.n,
                    **names,
                )
            )
        else:
            lines.append(t(lang, "stats_row_thin", n=agg.n, **names))
    if len(lines) == 2:
        lines.append(t(lang, "stats_no_rows"))
    if who_fp:
        lines += ["", t(lang, "who_fp", span=month_span(lang, who_fp))]
    if who_dec:
        lines += ["", t(lang, "who_dec", span=month_span(lang, who_dec))]
    rows = [
        [
            btn(t(lang, "btn_other_voiv"), Nav(to="stats")),
            btn(t(lang, "btn_other_purpose"), Pick(field="stats_voiv", value=voiv)),
        ],
        nav_row(lang),
    ]
    return "\n".join(lines), markup(rows)


# --- settings / calendar --------------------------------------------------


def settings_view(lang: str, current_lang: str, reminders: bool) -> Screen:
    state = t(lang, "state_on" if reminders else "state_off")
    rows = [
        [
            btn(
                t(lang, "btn_lang"),
                Act(action="lang", value="en" if current_lang == "ru" else "ru"),
            )
        ],
        [btn(t(lang, "btn_reminders", state=state), Act(action="reminders"))],
        [btn(t(lang, "btn_delete_all"), Act(action="del_all"))],
        nav_row(lang),
    ]
    return f"{t(lang, 'settings_title')}\n\n<i>{t(lang, 'reminders_note')}</i>", markup(rows)


def confirm_delete_all(lang: str) -> Screen:
    rows = [
        [
            btn(t(lang, "btn_yes_delete"), Act(action="del_all_yes")),
            btn(t(lang, "btn_no"), Nav(to="settings")),
        ],
        nav_row(lang),
    ]
    return t(lang, "confirm_delete_all"), markup(rows)


def calendar_view(lang: str, url: str | None) -> Screen:
    if not url:
        return t(lang, "calendar_soon"), markup([nav_row(lang)])
    rows = [[InlineKeyboardButton(text=t(lang, "btn_open_calendar"), url=url)], nav_row(lang)]
    return t(lang, "calendar_text"), markup(rows)


def wizard_prompt(lang: str, step: str) -> Screen:
    """Enum steps of the add-case wizard."""
    if step == "voiv":
        opts = [(str(v), voiv_label(v)) for v in Voivodeship]
        return t(lang, "ask_voiv"), enum_picker(lang, "voiv", opts, cols=2)
    if step == "purpose":
        opts = [(str(p), label(lang, "PURPOSE_BUTTONS", p)) for p in Purpose]
        return t(lang, "ask_purpose"), enum_picker(lang, "purpose", opts, cols=1)
    opts = [(str(c), label(lang, "CHANNEL_LABELS", c)) for c in Channel]
    return t(lang, "ask_channel"), enum_picker(lang, "channel", opts, cols=1)


def date_prompt(lang: str, milestone: Milestone) -> str:
    return t(
        lang,
        "ask_milestone_date",
        milestone=label(lang, "MILESTONE_LABELS", milestone),
        hint=label(lang, "MILESTONE_HINTS", milestone),
    )


def markup_one(lang: str, key: str, data) -> InlineKeyboardMarkup:
    return markup([[btn(t(lang, key), data)], nav_row(lang)])
