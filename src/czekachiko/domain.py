from enum import StrEnum


class Voivodeship(StrEnum):
    dolnoslaskie = "dolnoslaskie"
    kujawsko_pomorskie = "kujawsko_pomorskie"
    lubelskie = "lubelskie"
    lubuskie = "lubuskie"
    lodzkie = "lodzkie"
    malopolskie = "malopolskie"
    mazowieckie = "mazowieckie"
    opolskie = "opolskie"
    podkarpackie = "podkarpackie"
    podlaskie = "podlaskie"
    pomorskie = "pomorskie"
    slaskie = "slaskie"
    swietokrzyskie = "swietokrzyskie"
    warminsko_mazurskie = "warminsko_mazurskie"
    wielkopolskie = "wielkopolskie"
    zachodniopomorskie = "zachodniopomorskie"


class Purpose(StrEnum):
    """Basis of the application. Stored as is: never rename a value.

    New members go at the end, so code that walks the enum keeps its order.
    """

    praca = "praca"
    jdg = "jdg"
    studia = "studia"
    rodzina = "rodzina"
    inne = "inne"
    blue_card = "blue_card"
    staly = "staly"
    rezydent_ue = "rezydent_ue"


class PermitType(StrEnum):
    temporary = "temporary"  # pobyt czasowy
    permanent = "permanent"  # pobyt stały
    eu_resident = "eu_resident"  # rezydent długoterminowy UE


P, T = Purpose, PermitType
# Each permit type with its bases, in the order pickers show them.
PERMIT_GROUPS: dict[PermitType, tuple[Purpose, ...]] = {
    T.temporary: (P.praca, P.jdg, P.blue_card, P.studia, P.rodzina, P.inne),
    T.permanent: (P.staly,),
    T.eu_resident: (P.rezydent_ue,),
}
PERMIT_TYPE: dict[Purpose, PermitType] = {p: t for t, ps in PERMIT_GROUPS.items() for p in ps}
# Every purpose in picker order: the permit types one after another.
PURPOSE_ORDER: tuple[Purpose, ...] = tuple(p for ps in PERMIT_GROUPS.values() for p in ps)


def canonical(purposes) -> tuple[Purpose, ...]:
    """Distinct purposes in picker order."""
    chosen = {Purpose(p) for p in purposes}
    return tuple(p for p in PURPOSE_ORDER if p in chosen)


def group_of(purposes) -> PermitType | None:
    """The permit type whose bases are exactly these purposes, if any."""
    chosen = canonical(purposes)
    return next((t for t, ps in PERMIT_GROUPS.items() if ps == chosen), None)


class Channel(StrEnum):
    mos = "mos"
    paper = "paper"


class Milestone(StrEnum):
    filed = "filed"
    case_number = "case_number"
    braki = "braki"
    fingerprints = "fingerprints"
    decision = "decision"
    card = "card"


M = Milestone
FORECAST_TARGETS = (M.fingerprints, M.decision, M.card)
ANCHORS = (M.filed, M.fingerprints, M.decision)
INTERVAL_PAIRS = [
    (M.filed, M.case_number),
    (M.filed, M.braki),
    (M.filed, M.fingerprints),
    (M.filed, M.decision),
    (M.filed, M.card),
    (M.fingerprints, M.decision),
    (M.decision, M.card),
]
# Every milestone measured from the filing date: the chain shown on case and stats screens.
CHAIN = [(M.filed, m) for m in (M.case_number, M.braki, M.fingerprints, M.decision, M.card)]
# Milestones that must not precede each other, in order, when both are set.
ORDERED_CHAIN = (M.fingerprints, M.decision, M.card)
