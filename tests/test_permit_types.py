"""Permit types and their bases: the taxonomy, labels, checklists and stored values."""

from datetime import date

import pytest

from czekachiko import documents
from czekachiko.db.repo import calendar_payload
from czekachiko.domain import (
    PERMIT_GROUPS,
    PERMIT_TYPE,
    PURPOSE_ORDER,
    Milestone,
    PermitType,
    Purpose,
    canonical,
    group_of,
)
from czekachiko.locales import en, ru

P, T = Purpose, PermitType


def test_stored_values_of_existing_purposes_are_unchanged():
    # Cases in the database hold these strings; they must keep resolving.
    assert [p.value for p in Purpose][:5] == ["praca", "jdg", "studia", "rodzina", "inne"]
    assert {p.value for p in Purpose} >= {"blue_card", "staly", "rezydent_ue"}
    assert max(len(p.value) for p in Purpose) <= 16  # cases.purpose is VARCHAR(16)


def test_every_purpose_has_exactly_one_permit_type():
    assert set(PERMIT_TYPE) == set(Purpose)
    assert sorted(PURPOSE_ORDER) == sorted(Purpose)
    assert PERMIT_TYPE[P.praca] == PERMIT_TYPE[P.blue_card] == T.temporary
    assert PERMIT_TYPE[P.staly] == "permanent"
    assert PERMIT_TYPE[P.rezydent_ue] == "eu_resident"
    assert PERMIT_GROUPS[T.temporary] == (P.praca, P.jdg, P.blue_card, P.studia, P.rodzina, P.inne)


def test_canonical_and_group_of():
    assert canonical(["inne", "praca", "praca"]) == (P.praca, P.inne)
    assert group_of(PERMIT_GROUPS[T.temporary][::-1]) == T.temporary
    assert group_of([P.staly]) == T.permanent
    assert group_of([P.praca, P.jdg]) is None
    with pytest.raises(ValueError):
        canonical(["visa"])


@pytest.mark.parametrize("loc", [ru, en])
def test_labels_for_every_purpose_and_permit_type(loc):
    assert set(loc.PURPOSE_LABELS) == set(loc.PURPOSE_BUTTONS) == set(Purpose)
    assert set(loc.PERMIT_TYPE_LABELS) == set(loc.PERMIT_TYPE_BUTTONS) == set(PermitType)
    assert all(v and "art." not in v for v in loc.PERMIT_TYPE_LABELS.values())


def test_existing_labels_keep_their_words():
    # Calendar titles and shared cards are built from these: changing one retitles events.
    assert {p: ru.PURPOSE_LABELS[p] for p in list(Purpose)[:5]} == {
        P.praca: "работа",
        P.jdg: "бизнес (JDG)",
        P.studia: "учёба",
        P.rodzina: "семья",
        P.inne: "другое",
    }
    assert ru.PURPOSE_LABELS[P.blue_card] == "Blue Card"
    assert ru.PURPOSE_LABELS[P.staly] == "постоянный побыт"
    assert ru.PURPOSE_LABELS[P.rezydent_ue] == "резидент ЕС"


class _Case:
    def __init__(self, purpose):
        self.voivodeship, self.purpose = "mazowieckie", purpose

    def dates(self):
        return {"filed": date(2026, 3, 6), "fingerprints": date(2026, 6, 1)}


def test_calendar_titles():
    assert calendar_payload(_Case("jdg"), "fingerprints", date(2026, 6, 1))["title"] == (
        "Mazowieckie · бизнес (JDG) · отпечатки сданы"
    )
    payload = calendar_payload(_Case("rezydent_ue"), Milestone.fingerprints, date(2026, 6, 1))
    assert payload["title"] == "Mazowieckie · резидент ЕС · отпечатки сданы"
    assert payload["description"].startswith("Mazowieckie · резидент ЕС\n")


@pytest.mark.parametrize(
    ("purpose", "specific"),
    [
        (P.blue_card, ("zalacznik1", "umowa_praca", "dyplom")),
        (P.staly, ("podstawa_staly", "dochod")),
        (P.rezydent_ue, ("pobyt_5lat", "dochod", "jezyk_polski")),
    ],
)
def test_new_checklists(purpose, specific):
    codes = documents.checklist(purpose)
    assert codes == (*documents.CORE, *specific)
    assert "ubezpieczenie" in codes
    assert all(len(c) <= 32 for c in codes)  # case_documents.code is VARCHAR(32)


def test_unknown_basis_has_its_own_type():
    assert PERMIT_TYPE[P.nieznane] == T.unknown == "unknown"
    assert PERMIT_GROUPS[T.unknown] == (P.nieznane,)
    for t in (T.temporary, T.permanent, T.eu_resident):
        assert P.nieznane not in PERMIT_GROUPS[t]
    assert group_of([P.nieznane]) == T.unknown
    assert documents.checklist(P.nieznane) == documents.CORE
    assert ru.PURPOSE_LABELS[P.nieznane] == "другое основание / не указано"
    assert en.PURPOSE_LABELS[P.nieznane] == "other / not specified"
