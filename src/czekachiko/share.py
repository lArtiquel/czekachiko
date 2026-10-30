"""Inline sharing: voivodeship and purpose name matching, compact card codes. Pure."""

import unicodedata
from collections.abc import Iterable

from czekachiko.domain import (
    PERMIT_GROUPS,
    PERMIT_TYPE,
    PermitType,
    Purpose,
    Voivodeship,
    canonical,
    group_of,
)

MAX_COMPARE = 6
V = Voivodeship
# All of Poland, in share codes and in the API's voivodeship lists.
ALL = "all"
Place = Voivodeship | None

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
    Purpose.blue_card: ("blue", "блю", "niebiesk", "голуб"),
    Purpose.staly: ("staly", "постоян", "permanent"),
    Purpose.rezydent_ue: ("rezyden", "резидент", "resident"),
    Purpose.nieznane: ("nieznan", "unknown", "неизвест", "указан"),
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


def selector(purposes: Iterable[Purpose | str]) -> str:
    """Compact name of a purpose set: `jdg`, a permit type such as `temporary`, or `praca+jdg`.

    A single purpose keeps its own code, so codes made before permit types existed stay valid.
    """
    chosen = canonical(purposes)
    if len(chosen) == 1:
        return chosen[0].value
    group = group_of(chosen)
    return group.value if group is not None else "+".join(p.value for p in chosen)


def parse_selector(text: str) -> tuple[Purpose, ...] | None:
    """Purposes of a selector; None unless they are distinct and share one permit type."""
    if text in PermitType.__members__:
        return PERMIT_GROUPS[PermitType(text)]
    try:
        purposes = [Purpose(p) for p in text.split("+")]
    except ValueError:
        return None
    if len(set(purposes)) != len(purposes) or len({PERMIT_TYPE[p] for p in purposes}) != 1:
        return None
    return canonical(purposes)


def encode(purpose: str | Iterable[Purpose | str], voivs: list[Place]) -> str:
    """`s:<selector>:<places>`, places being voivodeship indexes or `all`, e.g. `s:jdg:6`."""
    sel = selector([purpose] if isinstance(purpose, str) else purpose)
    order = list(Voivodeship)
    return f"s:{sel}:" + ",".join(ALL if v is None else str(order.index(v)) for v in voivs)


def decode(code: str) -> tuple[str, list[Place]] | None:
    """(canonical selector, places) of a stats code; old `s:<purpose>:<indexes>` codes too."""
    parts = code.strip().split(":")
    if len(parts) != 3 or parts[0] != "s":
        return None
    purposes = parse_selector(parts[1])
    if purposes is None:
        return None
    try:
        order = list(Voivodeship)
        voivs = [None if i == ALL else order[int(i)] for i in parts[2].split(",") if i]
    except (ValueError, IndexError):
        return None
    if not voivs or len(voivs) > MAX_COMPARE:
        return None
    return selector(purposes), voivs
