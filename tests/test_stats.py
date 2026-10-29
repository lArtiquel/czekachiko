from datetime import date, timedelta

from czekachiko.domain import Milestone
from czekachiko.stats import aggregate, forecast, is_suspicious, percentile, who_now

M = Milestone
TODAY = date(2026, 10, 29)
TYPICAL = [90, 100, 120, 150, 170, 190, 210, 240]


def test_percentile_linear():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.9) == 10


def test_aggregate():
    assert aggregate([]) is None
    a = aggregate([100, 120, 140, 160, 180])
    assert (a.n, a.median, a.min, a.max) == (5, 140, 100, 180)


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
