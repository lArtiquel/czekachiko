"""Shareable stats cards: voivodeship name matching, compact codes and card text. Pure."""

import unicodedata

from czekachiko.domain import Purpose, Voivodeship
from czekachiko.i18n import label, t, voiv_label

MAX_COMPARE = 6
V = Voivodeship

# Prefixes people actually type: Polish (diacritics stripped), Russian, and the capital city.
ALIASES: dict[Voivodeship, tuple[str, ...]] = {
    V.dolnoslaskie: ("dolno", "нижнесилез", "wroclaw", "вроцлав"),
    V.kujawsko_pomorskie: ("kujaw", "куяв", "bydgoszcz", "быдгощ", "torun", "торун"),
    V.lubelskie: ("lubel", "lublin", "люблин"),
    V.lubuskie: ("lubus", "любуш", "zielona", "зелена", "gorzow", "гожув"),
    V.lodzkie: ("lodz", "лодз"),
    V.malopolskie: ("malopol", "малопол", "krakow", "краков"),
    V.mazowieckie: ("mazow", "мазов", "warszaw", "варшав", "warsaw"),
    V.opolskie: ("opol", "опол"),
    V.podkarpackie: ("podkarpac", "подкарпат", "rzeszow", "жешув"),
    V.podlaskie: ("podlas", "подляш", "bialystok", "белосток"),
    V.pomorskie: ("pomorsk", "поморск", "gdansk", "гданьск", "gdynia", "гдын"),
    V.slaskie: ("slask", "силез", "katowic", "катовиц"),
    V.swietokrzyskie: ("swieto", "свентокш", "kielce", "кельц"),
    V.warminsko_mazurskie: ("warmin", "варми", "olsztyn", "ольштын"),
    V.wielkopolskie: ("wielkopol", "великопол", "poznan", "познан"),
    V.zachodniopomorskie: ("zachodnio", "западнопомор", "szczecin", "щецин"),
}

PURPOSE_ALIASES: dict[Purpose, tuple[str, ...]] = {
    Purpose.praca: ("114", "praca", "prac", "работ", "work"),
    Purpose.jdg: ("142", "jdg", "biznes", "бизнес", "ип", "business", "działal", "dzialal"),
    Purpose.studia: ("studia", "stud", "учеб", "study"),
    Purpose.rodzina: ("rodzin", "семь", "family"),
}


def normalize(text: str) -> str:
    text = text.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _tokens(query: str) -> list[str]:
    return [tok for tok in normalize(query).replace(",", " ").split() if len(tok) >= 2]


def _matches(token: str, aliases: tuple[str, ...]) -> bool:
    return (
        any(a.startswith(token) or token.startswith(a) for a in aliases)
        if len(token) >= 3
        else (token in aliases)
    )


def match_voivodeships(query: str) -> list[Voivodeship]:
    toks = _tokens(query)
    return [v for v in Voivodeship if any(_matches(tok, ALIASES[v]) for tok in toks)]


def match_purposes(query: str) -> list[Purpose]:
    toks = _tokens(query)
    return [p for p in Purpose if any(_matches(tok, PURPOSE_ALIASES.get(p, ())) for tok in toks)]


def encode(purpose: str, voivs: list[Voivodeship]) -> str:
    order = list(Voivodeship)
    return f"s:{purpose}:" + ",".join(str(order.index(v)) for v in voivs)


def decode(code: str) -> tuple[str, list[Voivodeship]] | None:
    parts = code.strip().split(":")
    if len(parts) != 3 or parts[0] != "s":
        return None
    try:
        purpose = Purpose(parts[1])
        order = list(Voivodeship)
        voivs = [order[int(i)] for i in parts[2].split(",") if i]
    except (ValueError, IndexError):
        return None
    if not voivs or len(voivs) > MAX_COMPARE:
        return None
    return purpose.value, voivs


def card_text(lang: str, purpose: str, chains: dict[Voivodeship, dict]) -> str:
    from czekachiko.ui.screens import chain_lines

    title = t(lang, "card_title", purpose=label(lang, "PURPOSE_LABELS", Purpose(purpose)))
    parts = [title]
    for v, chain in chains.items():
        parts.append(f"<b>{voiv_label(v)}</b>\n" + "\n".join(chain_lines(lang, chain)))
    parts.append(f"<i>{t(lang, 'card_footer')}</i>")
    return "\n\n".join(parts)
