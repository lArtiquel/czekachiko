from datetime import date

from czekachiko import cards, i18n, keyboards
from czekachiko.domain import Milestone, Voivodeship
from czekachiko.locales import en, ru
from czekachiko.stats import Aggregate, Forecast

M = Milestone


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


def test_case_card_has_disclaimer_and_footer():
    for lang, loc in (("ru", ru), ("en", en)):
        text = cards.case_card(lang, FakeCase(), FORECAST, {})
        assert loc.MESSAGES["disclaimer"] in text
        assert text.startswith(loc.MESSAGES["case_card_title"])
        assert text.endswith(f"<i>{loc.MESSAGES['card_footer']}</i>")


def test_case_card_no_data():
    f = Forecast(kind="no_data", anchor=M.fingerprints, target=M.decision)
    assert ru.MESSAGES["fc_no_data"] in cards.case_card("ru", FakeCase(), f, {})


def test_case_card_shows_full_chain_with_counts():
    chain = {
        (M.filed, M.case_number): Aggregate(1, 195, 195, 195, 195, 195, 195),
        (M.filed, M.fingerprints): Aggregate(3, 150, 200, 230, 140, 237, 192),
    }
    text = cards.case_card("ru", FakeCase(), FORECAST, chain)
    assert "номер дела" in text and "195" in text and "(дел: 1)" in text
    assert "в среднем 192 дн." in text and "мин 140" in text and "макс 237" in text
    assert "вызов на отпечатки пальцев" in text and "(дел: 0)" in text
    assert "✅ отпечатки сданы — 02.06.2026 · 141 дн." in text


def test_stats_card_shows_rows_even_with_one_case():
    aggs = {(M.filed, M.case_number): Aggregate(1, 195, 195, 195, 195, 195, 195)}
    text = cards.stats_card("ru", "jdg", {Voivodeship.mazowieckie: aggs})
    assert "в среднем 195 дн." in text and "(дел: 1)" in text
    assert "decyzja" in text and "(дел: 0)" in text


def test_purpose_labels_are_plain_words():
    for loc in (ru, en):
        for v in loc.PURPOSE_LABELS.values():
            assert "art." not in v


def test_launcher_is_one_web_app_button():
    ((button,),) = keyboards.launcher("ru", "https://example.org/").inline_keyboard
    assert button.text == "🚀 Открыть Czekachiko"
    assert button.web_app.url == "https://example.org/"


def test_feedback_prompt_has_only_cancel():
    ((button,),) = keyboards.feedback_cancel("ru").inline_keyboard
    assert button.text == "✖️ Отмена" and button.callback_data == keyboards.FEEDBACK_CANCEL
