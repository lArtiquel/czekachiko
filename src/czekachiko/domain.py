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
    praca = "praca"
    jdg = "jdg"
    studia = "studia"
    rodzina = "rodzina"
    inne = "inne"


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
