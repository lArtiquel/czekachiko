"""Russian copy. Labels here are also used for the public calendar."""

from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

V, P, M = Voivodeship, Purpose, Milestone

VOIV_LABELS = {
    V.dolnoslaskie: "Dolnośląskie",
    V.kujawsko_pomorskie: "Kujawsko-pomorskie",
    V.lubelskie: "Lubelskie",
    V.lubuskie: "Lubuskie",
    V.lodzkie: "Łódzkie",
    V.malopolskie: "Małopolskie",
    V.mazowieckie: "Mazowieckie",
    V.opolskie: "Opolskie",
    V.podkarpackie: "Podkarpackie",
    V.podlaskie: "Podlaskie",
    V.pomorskie: "Pomorskie",
    V.slaskie: "Śląskie",
    V.swietokrzyskie: "Świętokrzyskie",
    V.warminsko_mazurskie: "Warmińsko-mazurskie",
    V.wielkopolskie: "Wielkopolskie",
    V.zachodniopomorskie: "Zachodniopomorskie",
}

PURPOSE_LABELS = {
    P.praca: "art. 114",
    P.jdg: "art. 142",
    P.studia: "учёба",
    P.rodzina: "семья",
    P.inne: "другое",
}

MILESTONE_LABELS = {
    M.filed: "подача",
    M.case_number: "номер дела",
    M.braki: "wezwanie о brakach",
    M.fingerprints: "отпечатки",
    M.decision: "decyzja",
    M.card: "карта",
}

CHANNEL_LABELS = {Channel.mos: "MOS (онлайн)", Channel.paper: "Лично / почтой"}
