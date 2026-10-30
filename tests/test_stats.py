from datetime import date, timedelta

from czekachiko.domain import Milestone
from czekachiko.stats import aggregate, forecast, is_suspicious, percentile, plan, who_now

M = Milestone
TODAY = date(2026, 10, 29)
TYPICAL = [90, 100, 120, 150, 170, 190, 210, 240]


def test_percentile_linear():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.9) == 10


def test_aggregate():
    assert aggregate([]) is None
    a = aggregate([100, 120, 140, 160, 180])
    assert (a.n, a.median, a.min, a.max, a.mean) == (5, 140, 100, 180, 140)


def test_outlier_detection():
    assert is_suspicious(610, TYPICAL) is True
    assert is_suspicious(260, TYPICAL) is False


def test_outlier_needs_eight_values():
    assert is_suspicious(10_000, TYPICAL[:7]) is False


def test_outlier_zero_iqr_uses_floor():
    assert is_suspicious(150, [150] * 10) is False
    assert is_suspicious(400, [150] * 10) is True


def lookup_from(table):
    return lambda scope, a, b: table.get((scope, a, b), [])


FP_DEC = list(range(100, 281, 20))  # 10 values


def test_forecast_window_from_latest_anchor():
    case = {M.filed: TODAY - timedelta(days=200), M.fingerprints: TODAY - timedelta(days=50)}
    f = forecast(case, TODAY, lookup_from({("voiv", M.fingerprints, M.decision): FP_DEC}))
    assert (f.kind, f.scope, f.anchor, f.target) == ("window", "voiv", M.fingerprints, M.decision)
    assert f.start >= TODAY and f.start <= f.likely <= f.end
    assert (f.fastest, f.slowest) == (100, 280)


def test_forecast_waited_longer():
    case = {M.filed: TODAY - timedelta(days=400), M.fingerprints: TODAY - timedelta(days=300)}
    f = forecast(case, TODAY, lookup_from({("voiv", M.fingerprints, M.decision): FP_DEC}))
    assert (f.kind, f.waited_longer_than, f.total) == ("waited_longer", 10, 10)


def test_forecast_falls_back_to_national():
    case = {M.filed: TODAY - timedelta(days=30)}
    table = {
        ("voiv", M.filed, M.fingerprints): [100, 120, 140],
        ("national", M.filed, M.fingerprints): [100, 120, 140, 160, 180, 200],
    }
    f = forecast(case, TODAY, lookup_from(table))
    assert (f.kind, f.scope) == ("window", "national")


def test_forecast_falls_back_to_filed_anchor():
    case = {M.filed: TODAY - timedelta(days=200), M.fingerprints: TODAY - timedelta(days=10)}
    table = {("voiv", M.filed, M.decision): list(range(250, 451, 25))}
    f = forecast(case, TODAY, lookup_from(table))
    assert (f.kind, f.scope, f.anchor) == ("window", "voiv_filed", M.filed)


def test_plan_tries_the_channel_first_then_every_channel():
    case = {M.filed: TODAY - timedelta(days=200), M.fingerprints: TODAY - timedelta(days=10)}
    target, anchor, attempts = plan(case, by_channel=True)
    assert (target, anchor) == (M.decision, M.fingerprints)
    assert [label for _, label, _ in attempts] == [
        "voiv",
        "voiv_filed",
        "voiv_group",
        "national",
        "national_group",
        "voiv_any",
        "voiv_filed_any",
        "voiv_group_any",
        "national_any",
        "national_group_any",
    ]
    assert [scope for scope, _, _ in attempts][5:] == [
        "voiv_any",
        "voiv_any",
        "voiv_group_any",
        "national_any",
        "national_group_any",
    ]
    # Without the channel (inline cards) the plan is the channel-less one, as before.
    assert [label for _, label, _ in plan(case)[2]] == [
        "voiv",
        "voiv_filed",
        "voiv_group",
        "national",
        "national_group",
    ]
    single = plan(case, with_group=False, by_channel=True)[2]
    assert [label for _, label, _ in single] == [
        "voiv",
        "voiv_filed",
        "national",
        "voiv_any",
        "voiv_filed_any",
        "national_any",
    ]


def test_forecast_falls_back_to_every_channel():
    case = {M.filed: TODAY - timedelta(days=30)}
    table = {
        ("national_group", M.filed, M.fingerprints): [100, 120, 140],  # too few
        ("voiv_any", M.filed, M.fingerprints): [100, 120, 140, 160, 180, 200],
    }
    f = forecast(case, TODAY, lookup_from(table), by_channel=True)
    assert (f.kind, f.scope) == ("window", "voiv_any")


def test_forecast_by_channel_keeps_waited_longer():
    # Enough values for the channel itself: waiting past them all says so, no fallback.
    case = {M.filed: TODAY - timedelta(days=400), M.fingerprints: TODAY - timedelta(days=300)}
    table = {
        ("voiv", M.fingerprints, M.decision): FP_DEC,
        ("voiv_any", M.fingerprints, M.decision): list(range(100, 1000, 50)),
    }
    f = forecast(case, TODAY, lookup_from(table), by_channel=True)
    assert (f.kind, f.scope, f.waited_longer_than) == ("waited_longer", "voiv", 10)


def test_forecast_by_channel_no_data():
    f = forecast({M.filed: TODAY - timedelta(days=30)}, TODAY, lookup_from({}), by_channel=True)
    assert (f.kind, f.scope) == ("no_data", None)


def test_forecast_no_data():
    f = forecast({M.filed: TODAY - timedelta(days=30)}, TODAY, lookup_from({}))
    assert f.kind == "no_data" and f.target == M.fingerprints


def test_forecast_none_when_card_received():
    case = {
        M.filed: date(2025, 1, 1),
        M.fingerprints: date(2025, 3, 1),
        M.decision: date(2025, 9, 1),
        M.card: date(2025, 10, 1),
    }
    assert forecast(case, TODAY, lookup_from({})) is None


def test_who_now_span():
    events = [
        (TODAY - timedelta(days=3), date(2026, 3, 12)),
        (TODAY - timedelta(days=10), date(2026, 4, 2)),
        (TODAY - timedelta(days=20), date(2026, 3, 30)),
        (TODAY - timedelta(days=40), date(2025, 1, 1)),  # outside window
    ]
    assert who_now(events, TODAY) == (date(2026, 3, 1), date(2026, 4, 1))


def test_who_now_needs_three():
    events = [(TODAY, date(2026, 3, 1)), (TODAY, date(2026, 4, 1))]
    assert who_now(events, TODAY) is None
