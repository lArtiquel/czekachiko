from dataclasses import dataclass
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
    nieznane = "nieznane"  # basis not given, so the permit type is unknown too


class PermitType(StrEnum):
    temporary = "temporary"  # pobyt czasowy
    permanent = "permanent"  # pobyt stały
    eu_resident = "eu_resident"  # rezydent długoterminowy UE
    unknown = "unknown"  # not given: never pooled with the types above


P, T = Purpose, PermitType
# Each permit type with its bases, in the order pickers show them.
PERMIT_GROUPS: dict[PermitType, tuple[Purpose, ...]] = {
    T.temporary: (P.praca, P.jdg, P.blue_card, P.studia, P.rodzina, P.inne),
    T.permanent: (P.staly,),
    T.eu_resident: (P.rezydent_ue,),
    T.unknown: (P.nieznane,),
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
    """How the application was filed. Stored as is: never rename a value."""

    in_person = "in_person"  # at the office's counter
    post = "post"  # by post or e-Doręczenia
    mos = "mos"  # online, through MOS
    unknown = "unknown"  # imported cases whose source does not say; never offered in the app
    # The name of `post` before 0010 split the old "paper" value. An alias, not a member: it
    # is not iterated, and "paper" is no longer a stored value.
    paper = "post"


# What people can pick, in picker order.
USER_CHANNELS = (Channel.in_person, Channel.post, Channel.mos)


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


@dataclass(frozen=True)
class Step:
    milestone: Milestone
    optional: bool = False  # may never happen (a wezwanie in an in-person case)
    at_filing: bool = False  # usually happens on the filing day itself


# The order milestones happen in for each channel; the case timeline and the stats chain
# follow it. In person, fingerprints are usually given at the counter and a wezwanie is the
# exception. By post, e-Doręczenia or MOS, a call comes first and fingerprints follow it.
_CALLED = tuple(Step(m) for m in Milestone)
CHANNEL_PATHS: dict[Channel, tuple[Step, ...]] = {
    Channel.in_person: (
        Step(M.filed),
        Step(M.fingerprints, at_filing=True),
        Step(M.case_number),
        Step(M.braki, optional=True),
        Step(M.decision),
        Step(M.card),
    ),
    Channel.post: _CALLED,
    Channel.mos: _CALLED,
    Channel.unknown: _CALLED,
}


def channel_path(channel: Channel | str) -> tuple[Step, ...]:
    """The channel's path; anything unrecognised gets the post path (the milestone order)."""
    return CHANNEL_PATHS.get(channel, _CALLED)


# Milestones that cannot fall on the filing day itself, unless the channel's path takes them
# at filing (fingerprints in person). A 0-day interval from filing to one of them is a typo:
# statistics leave it out, the stored date stays.
NEVER_SAME_DAY = (M.case_number, M.braki, M.fingerprints)
# For each of them, the channels that do take it on the filing day.
SAME_DAY_CHANNELS: dict[Milestone, tuple[Channel, ...]] = {
    m: tuple(
        ch for ch in Channel if any(st.at_filing and st.milestone == m for st in channel_path(ch))
    )
    for m in NEVER_SAME_DAY
}


def zero_day_possible(milestone: Milestone | str, channel: Channel | str | None) -> bool:
    """Whether `milestone` can really come 0 days after filing in a case filed this way."""
    if milestone not in NEVER_SAME_DAY:
        return True
    return channel in SAME_DAY_CHANNELS[Milestone(milestone)]
