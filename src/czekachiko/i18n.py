from types import ModuleType

from czekachiko.locales import en, ru

LOCALES: dict[str, ModuleType] = {"ru": ru, "en": en}
DEFAULT = "ru"


def loc(lang: str | None) -> ModuleType:
    return LOCALES.get(lang or DEFAULT, ru)


def t(lang: str | None, key: str, **kw) -> str:
    text = loc(lang).MESSAGES[key]
    return text.format(**kw) if kw else text


def voiv_label(voiv: str) -> str:
    from czekachiko.domain import Voivodeship

    return ru.VOIV_LABELS[Voivodeship(voiv)]


def label(lang: str | None, table: str, key) -> str:
    """Look up a label table (PURPOSE_LABELS, MILESTONE_LABELS, ...) for the language."""
    return getattr(loc(lang), table)[key]
