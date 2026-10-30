"""Filing channels: the stored values, what the app offers, and each channel's path."""

from czekachiko.domain import (
    CHANNEL_PATHS,
    USER_CHANNELS,
    Channel,
    Milestone,
    channel_path,
)
from czekachiko.locales import en, ru

C, M = Channel, Milestone


def test_stored_values():
    assert [c.value for c in Channel] == ["in_person", "post", "mos", "unknown"]
    assert max(len(c.value) for c in Channel) <= 16  # cases.channel is VARCHAR(16)
    # "paper" went away in 0010: it no longer resolves as a stored value.
    assert "paper" not in {c.value for c in Channel}


def test_the_app_offers_three_channels_never_unknown():
    assert list(USER_CHANNELS) == [C.in_person, C.post, C.mos]


def test_in_person_gives_fingerprints_at_filing_and_braki_is_optional():
    path = CHANNEL_PATHS[C.in_person]
    assert [s.milestone for s in path] == [
        M.filed,
        M.fingerprints,
        M.case_number,
        M.braki,
        M.decision,
        M.card,
    ]
    assert [s.milestone for s in path if s.at_filing] == [M.fingerprints]
    assert [s.milestone for s in path if s.optional] == [M.braki]


def test_post_and_mos_wait_for_a_call_then_fingerprints():
    expected = [M.filed, M.case_number, M.braki, M.fingerprints, M.decision, M.card]
    for channel in (C.post, C.mos):
        path = CHANNEL_PATHS[channel]
        assert [s.milestone for s in path] == expected
        assert not any(s.optional or s.at_filing for s in path)


def test_every_path_holds_every_milestone_once():
    for channel in Channel:
        assert sorted(s.milestone for s in channel_path(channel)) == sorted(Milestone)


def test_unknown_and_unrecognised_channels_use_the_post_path():
    assert channel_path(C.unknown) == CHANNEL_PATHS[C.post]
    assert channel_path("something-else") == CHANNEL_PATHS[C.post]
    assert channel_path("in_person") == CHANNEL_PATHS[C.in_person]


def test_labels_in_both_languages():
    for loc in (ru, en):
        assert set(loc.CHANNEL_LABELS) == set(Channel)
    assert ru.CHANNEL_LABELS[C.in_person] == "Лично в urzędzie"
    assert ru.CHANNEL_LABELS[C.post] == "Почта или e-Doręczenia"
    assert ru.CHANNEL_LABELS[C.mos] == "MOS (онлайн)"
