from datetime import date

from aiogram.types import InlineKeyboardMarkup

from czekachiko import i18n
from czekachiko.domain import Milestone
from czekachiko.locales import en, ru
from czekachiko.stats import Aggregate, Forecast
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Day, Nav, date_picker

M = Milestone
TODAY = date(2026, 10, 29)
MENU = Nav(to="menu").pack()


def buttons(markup: InlineKeyboardMarkup):
    return [b for row in markup.inline_keyboard for b in row]


class FakeCase:
    id = 7
    voivodeship = "malopolskie"
    purpose = "praca"
    channel = "mos"

    def dates(self):
        return {M.filed: date(2026, 1, 12), M.fingerprints: date(2026, 6, 2)}


FORECAST = Forecast(
    kind="window",
    anchor=M.fingerprints,
    target=M.decision,
    start=date(2026, 11, 20),
    likely=date(2027, 2, 1),
    end=date(2027, 5, 1),
    n=12,
    scope="voiv",
    fastest=90,
    slowest=400,
)


def test_locales_have_same_keys():
    assert set(ru.MESSAGES) == set(en.MESSAGES)


def test_t_falls_back_to_ru():
    assert i18n.t("de", "menu_title") == ru.MESSAGES["menu_title"]


def test_date_picker_disables_future():
    markup = date_picker("ru", 2026, 10, TODAY)
    packed = {b.callback_data for b in buttons(markup)}
    assert Day(y=2026, m=10, d=29).pack() in packed
    assert Day(y=2026, m=10, d=30).pack() not in packed
    assert not any(b.text == "›" for b in buttons(markup))


def test_date_picker_past_month_has_next_arrow():
    assert any(b.text == "›" for b in buttons(date_picker("ru", 2026, 9, TODAY)))


def all_screens(lang):
    case = FakeCase()
    agg = Aggregate(10, 90, 170, 240, 60, 400, 165)
    return [
        screens.privacy(lang),
        screens.help_view(lang),
        screens.cases_list(lang, [case]),
        screens.case_view(lang, case, FORECAST),
        screens.milestone_picker(lang, case),
        screens.stats_view(
            lang, "mazowieckie", "jdg", {(M.filed, M.fingerprints): agg}, None, None
        ),
        screens.settings_view(lang, "ru", False),
        screens.calendar_view(lang, None),
        screens.outlier_prompt(lang, 7, "mazowieckie", M.filed, M.fingerprints, agg, 610),
        screens.confirm_delete_case(lang, 7),
        screens.confirm_delete_all(lang),
    ]


def test_every_screen_has_menu_button():
    for lang in ("ru", "en"):
        for text, markup in all_screens(lang):
            assert text
            assert MENU in {b.callback_data for b in buttons(markup)}, text[:40]


def test_case_view_has_disclaimer():
    assert ru.MESSAGES["disclaimer"] in screens.case_view("ru", FakeCase(), FORECAST)[0]
    assert en.MESSAGES["disclaimer"] in screens.case_view("en", FakeCase(), FORECAST)[0]


def test_case_view_no_data():
    f = Forecast(kind="no_data", anchor=M.fingerprints, target=M.decision)
    text, _ = screens.case_view("ru", FakeCase(), f)
    assert ru.MESSAGES["fc_no_data"] in text


def test_outlier_prompt_mentions_range():
    agg = Aggregate(10, 90, 170, 240, 60, 400, 165)
    text, _ = screens.outlier_prompt("ru", 7, "mazowieckie", M.filed, M.fingerprints, agg, 610)
    assert "90" in text and "240" in text and "610" in text


def test_main_menu_has_dog():
    assert "🐕" in screens.main_menu("ru")[0]


def test_main_menu_has_share_button():
    from urllib.parse import parse_qs, urlparse

    _, kb = screens.main_menu("ru")
    share = [b for b in buttons(kb) if b.url and b.url.startswith("https://t.me/share/url")]
    assert len(share) == 1
    q = parse_qs(urlparse(share[0].url).query)
    assert q["url"] == ["https://t.me/czekachiko_bot"]
    assert "karta pobytu" in q["text"][0]


def test_case_view_shows_full_chain_with_counts():
    chain = {
        (M.filed, M.case_number): Aggregate(1, 195, 195, 195, 195, 195, 195),
        (M.filed, M.fingerprints): Aggregate(3, 150, 200, 230, 140, 237, 192),
    }
    text, _ = screens.case_view("ru", FakeCase(), FORECAST, chain)
    assert "номер дела" in text and "195" in text and "(дел: 1)" in text
    assert "в среднем 192 дн." in text and "мин 140" in text and "макс 237" in text
    assert "wezwanie о brakach" in text and "(дел: 0)" in text
    assert "карта" in text


def test_stats_view_shows_rows_even_with_one_case():
    aggs = {(M.filed, M.case_number): Aggregate(1, 195, 195, 195, 195, 195, 195)}
    text, _ = screens.stats_view("ru", "mazowieckie", "jdg", aggs, None, None)
    assert "в среднем 195 дн." in text and "(дел: 1)" in text
    assert "decyzja" in text and "(дел: 0)" in text
