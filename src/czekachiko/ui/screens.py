"""Pure screen renderers: data in, (text, keyboard) out."""

from datetime import date
from html import escape
from urllib.parse import quote, urlencode

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from czekachiko import documents
from czekachiko.cards import case_title, chain_lines, fmt, forecast_text
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.i18n import label, loc, t, voiv_label
from czekachiko.stats import Aggregate, Forecast
from czekachiko.ui.keyboards import (
    Act,
    Nav,
    Pick,
    btn,
    cancel_row,
    date_picker,
    enum_picker,
    markup,
    nav_row,
    open_app,
    send_to_chat,
)

Screen = tuple[str, InlineKeyboardMarkup]
BOT_URL = "https://t.me/czekachiko_bot"
M = Milestone


def month_span(lang: str, span: tuple[date, date]) -> str:
    months = loc(lang).MONTHS
    a, b = span
    fa, fb = f"{months[a.month - 1].lower()} {a.year}", f"{months[b.month - 1].lower()} {b.year}"
    return fa if a == b else f"{fa} – {fb}"


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
        [
            InlineKeyboardButton(text=t(lang, "btn_share"), url=share_url(lang)),
            btn(t(lang, "btn_feedback"), Nav(to="feedback")),
        ],
    ]
    return t(lang, "menu_title"), markup(rows)


def share_url(lang: str) -> str:
    """Telegram's native "forward to a chat" picker with just the bot link."""
    return "https://t.me/share/url?" + urlencode({"url": BOT_URL}, quote_via=quote)


def privacy(lang: str) -> Screen:
    return t(lang, "privacy"), markup([nav_row(lang)])


def feedback_prompt(lang: str) -> Screen:
    rows = [
        [btn(t(lang, "btn_cancel"), Act(action="cancel")), btn(t(lang, "btn_menu"), Nav(to="menu"))]
    ]
    return t(lang, "feedback_prompt"), markup(rows)


def share_view(lang: str) -> Screen:
    rows = [[InlineKeyboardButton(text=t(lang, "btn_share"), url=share_url(lang))], nav_row(lang)]
    return t(lang, "share_prompt"), markup(rows)


def start_text(lang: str) -> str:
    return t(lang, "menu_title")


def start_view(lang: str, webapp_url: str) -> Screen:
    """/start: one message whose only button opens the Mini App."""
    return start_text(lang), open_app(lang, webapp_url)


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


def case_view(
    lang: str,
    case,
    f: Forecast | None,
    chain: dict | None = None,
    docs: tuple[int, int] | None = None,
) -> Screen:
    """docs: (ticked, total) for the owner's checklist; None leaves the line out."""
    dates = case.dates()
    channel = label(lang, "CHANNEL_LABELS", Channel(case.channel))
    filed = dates[M.filed]
    lines = [
        f"<b>{case_title(lang, case)}</b> · {channel}",
        f"📨 {label(lang, 'MILESTONE_LABELS', M.filed)} — {fmt(filed)}",
    ]
    if docs is not None:
        lines.append(t(lang, "docs_progress", done=docs[0], total=docs[1]))
    lines += ["", *chain_lines(lang, chain or {}, dates)]
    lines += ["", forecast_text(lang, case, f), "", t(lang, "disclaimer")]
    rows = [
        [
            btn(t(lang, "btn_mark"), Nav(to="mark", case_id=case.id)),
            btn(t(lang, "btn_docs"), Nav(to="docs", case_id=case.id)),
        ],
        [send_to_chat(lang, f"c:{case.id}")],
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


# --- documents -----------------------------------------------------------
# Custom names are free text. Message text is parsed as HTML, so names are escaped there;
# button labels are plain text and take the raw name.


def docs_view(lang: str, case, docs: list, notice: str | None = None) -> Screen:
    """Buttons tick every item; the text lists what was sent, with dates (text wraps,
    button labels get cut off)."""
    std = {d.code: d.submitted_on for d in docs if d.code is not None}
    # (label, submitted_on, callback value): the purpose's list first, then the owner's own.
    items = [(documents.doc_name(c), std.get(c), c) for c in documents.checklist(case.purpose)]
    items += [(d.name, d.submitted_on, str(d.id)) for d in docs if d.name is not None]
    done, total = documents.progress(case.purpose, docs)
    lines = [t(lang, "docs_title", done=done, total=total), case_title(lang, case), ""]
    sent = [f"✅ {escape(name)} — {fmt(d)}" for name, d, _ in items if d]
    lines += [*sent, ""] if sent else []
    lines += [f"<i>{t(lang, 'docs_note')}</i>", t(lang, "docs_hint")]
    if notice:
        lines[:0] = [notice, ""]
    rows = [
        [btn(f"{'✅' if d else '⬜'} {name}", Pick(field="doc", value=v, case_id=case.id))]
        for name, d, v in items
    ]
    rows.append([btn(t(lang, "btn_doc_add"), Act(action="doc_add", case_id=case.id))])
    rows.append(nav_row(lang, Nav(to="case", case_id=case.id)))
    return "\n".join(lines), markup(rows)


def doc_item_view(lang: str, case_id: int, doc) -> Screen:
    """One of the owner's own documents: date, rename, delete."""
    d = doc.submitted_on
    status = t(lang, "doc_sent", date=fmt(d)) if d else t(lang, "doc_not_sent")
    v = str(doc.id)
    rows = [
        [btn(t(lang, "btn_doc_date"), Act(action="doc_date", case_id=case_id, value=v))],
        [
            btn(t(lang, "btn_doc_rename"), Act(action="doc_ren", case_id=case_id, value=v)),
            btn(t(lang, "btn_doc_delete"), Act(action="doc_del", case_id=case_id, value=v)),
        ],
        nav_row(lang, Nav(to="docs", case_id=case_id)),
    ]
    return f"📄 <b>{escape(doc.name)}</b>\n{status}", markup(rows)


def doc_name_prompt(
    lang: str, case_id: int, rename: bool = False, error: str | None = None
) -> Screen:
    text = t(lang, "doc_ask_rename" if rename else "doc_ask_name", max=documents.MAX_NAME)
    if error:
        text = f"⚠️ {error}\n\n{text}"
    rows = [[btn(t(lang, "btn_back"), Nav(to="docs", case_id=case_id)), *cancel_row(lang)]]
    return text, markup(rows)


def doc_date_prompt(
    lang: str,
    case_id: int,
    name: str,
    year: int,
    month: int,
    today: date,
    can_clear: bool = False,
    error: str | None = None,
) -> Screen:
    text = t(lang, "doc_ask_date", name=escape(name))
    if error:
        text = f"⚠️ {error}\n\n{text}"
    back = Nav(to="docs", case_id=case_id)
    return text, date_picker(lang, year, month, today, can_clear=can_clear, back=back)


def confirm_delete_doc(lang: str, case_id: int, doc) -> Screen:
    v = str(doc.id)
    rows = [
        [
            btn(t(lang, "btn_yes_delete"), Act(action="doc_del_yes", case_id=case_id, value=v)),
            btn(t(lang, "btn_no"), Pick(field="doc", value=v, case_id=case_id)),
        ],
        nav_row(lang, Nav(to="docs", case_id=case_id)),
    ]
    return t(lang, "confirm_delete_doc", name=escape(doc.name)), markup(rows)


# --- stats ---------------------------------------------------------------


def encode_stats(purpose: str, voiv: str) -> str:
    from czekachiko.share import encode

    return encode(str(purpose), [Voivodeship(voiv)])


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
    lines = [title, "", t(lang, "chain_title"), "", *chain_lines(lang, aggregates)]
    if who_fp:
        lines += ["", t(lang, "who_fp", span=month_span(lang, who_fp))]
    if who_dec:
        lines += ["", t(lang, "who_dec", span=month_span(lang, who_dec))]
    rows = [
        [send_to_chat(lang, encode_stats(purpose, voiv))],
        [btn(t(lang, "btn_compare"), Nav(to="compare"))],
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


def calendar_url(calendar_id: str) -> str:
    return "https://calendar.google.com/calendar/embed?" + urlencode(
        {"src": calendar_id, "ctz": "Europe/Warsaw"}, quote_via=quote
    )


def calendar_view(lang: str, links: dict[str, str] | None) -> Screen:
    """One public calendar per voivodeship."""
    voivs = [
        InlineKeyboardButton(text=voiv_label(v), url=calendar_url(links[v.value]))
        for v in Voivodeship
        if links and v.value in links
    ]
    if not voivs:
        return t(lang, "calendar_soon"), markup([nav_row(lang)])
    rows = [voivs[i : i + 2] for i in range(0, len(voivs), 2)]
    rows.append(nav_row(lang))
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
