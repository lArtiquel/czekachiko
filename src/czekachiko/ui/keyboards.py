import calendar
from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from czekachiko.dates import EARLIEST
from czekachiko.i18n import loc, t


class Nav(CallbackData, prefix="n"):
    to: str  # menu | cases | case | add | stats | calendar | settings | help | privacy
    case_id: int = 0


class Pick(CallbackData, prefix="p"):
    field: str  # voiv | purpose | channel | milestone | stats_voiv | stats_purpose
    value: str
    case_id: int = 0


class Day(CallbackData, prefix="d"):
    y: int
    m: int
    d: int


class Month(CallbackData, prefix="mo"):
    y: int
    m: int


class Act(CallbackData, prefix="a"):
    action: str
    case_id: int = 0
    value: str = ""


class Noop(CallbackData, prefix="x"):
    pass


NOOP = Noop().pack()


def btn(text: str, data: CallbackData | str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=data if isinstance(data, str) else data.pack()
    )


def nav_row(lang: str, back: CallbackData | None = None) -> list[InlineKeyboardButton]:
    row = [btn(t(lang, "btn_back"), back)] if back is not None else []
    row.append(btn(t(lang, "btn_menu"), Nav(to="menu")))
    return row


def cancel_row(lang: str) -> list[InlineKeyboardButton]:
    return [
        btn(t(lang, "btn_cancel"), Act(action="cancel")),
        btn(t(lang, "btn_menu"), Nav(to="menu")),
    ]


def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grid(buttons: list[InlineKeyboardButton], cols: int) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + cols] for i in range(0, len(buttons), cols)]


def enum_picker(
    lang: str,
    field: str,
    options: list[tuple[str, str]],
    cols: int = 2,
    case_id: int = 0,
    back: CallbackData | None = None,
    cancel: bool = True,
) -> InlineKeyboardMarkup:
    """options: (value, label)."""
    rows = grid(
        [btn(label, Pick(field=field, value=v, case_id=case_id)) for v, label in options], cols
    )
    rows.append(cancel_row(lang) if cancel else nav_row(lang, back))
    return markup(rows)


def _add_months(y: int, m: int, delta: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) + delta
    return total // 12, total % 12 + 1


def date_picker(
    lang: str, year: int, month: int, today: date, can_clear: bool = False
) -> InlineKeyboardMarkup:
    L = loc(lang)
    rows: list[list[InlineKeyboardButton]] = []
    prev_y, prev_m = _add_months(year, month, -1)
    next_y, next_m = _add_months(year, month, 1)
    header = [btn(f"{L.MONTHS[month - 1]} {year}", NOOP)]
    if date(prev_y, prev_m, 1) >= EARLIEST.replace(day=1):
        header.insert(0, btn("‹", Month(y=prev_y, m=prev_m)))
    if date(next_y, next_m, 1) <= today.replace(day=1):
        header.append(btn("›", Month(y=next_y, m=next_m)))
    rows.append(header)
    rows.append([btn(w, NOOP) for w in L.WEEKDAYS])
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(btn(" ", NOOP))
            elif date(year, month, d) > today:
                row.append(btn("·", NOOP))
            else:
                row.append(btn(str(d), Day(y=year, m=month, d=d)))
        rows.append(row)
    quick = [
        btn(t(lang, "btn_today"), Act(action="today")),
        btn(t(lang, "btn_yesterday"), Act(action="yesterday")),
    ]
    rows.append(quick)
    if can_clear:
        rows.append([btn(t(lang, "btn_clear_date"), Act(action="clear_date"))])
    rows.append(cancel_row(lang))
    return markup(rows)


REPLY_MENU = [
    ["btn_add", "btn_cases"],
    ["btn_stats", "btn_calendar"],
    ["btn_settings", "btn_help"],
    ["btn_share"],
]


def reply_menu(lang: str) -> ReplyKeyboardMarkup:
    """Always-visible menu under the input field."""
    rows = [[KeyboardButton(text=t(lang, key)) for key in row] for row in REPLY_MENU]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
