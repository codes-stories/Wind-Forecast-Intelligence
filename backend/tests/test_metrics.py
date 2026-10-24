"""MAE / RMSE / bias / MAPE and coverage accounting."""
import math
from datetime import date, timezone

from tests.conftest import dt
from app.models.records import IntervalPoint, STATUS_ACTUAL_ONLY, STATUS_MATCHED
from app.services.metrics_service import compute_stats

UTC = timezone.utc


def point(status, actual, forecast, day=15, hour=0, minute=0):
    ts = dt(day, hour, minute)
    return IntervalPoint(
        timestamp=ts,
        settlement_date=date(2026, 1, day),
        settlement_period=None,
        actual_mw=actual,
        forecast_mw=forecast,
        status=status,
        forecast_publish_time=dt(14, 7, 30),
    )


def test_mae_rmse_and_signed_bias_are_hand_verifiable():
    points = [
        point(STATUS_MATCHED, actual=100, forecast=120),  # error +20
        point(STATUS_MATCHED, actual=200, forecast=170),  # error -30
    ]
    stats = compute_stats(points, expected_count=2, grain="hourly")
    assert stats.mae_mw == 25.0  # (20+30)/2
    assert stats.rmse_mw == round(math.sqrt(650), 3)  # sqrt((400+900)/2)
    assert stats.bias_mw == -5.0  # mean(forecast - actual)
    assert stats.n_matched == 2
    assert stats.coverage_pct == 100.0
    assert stats.coverage_complete is True


def test_bias_sign_convention_is_forecast_minus_actual():
    over = compute_stats([point(STATUS_MATCHED, 100, 150)], 1, "hourly")
    under = compute_stats([point(STATUS_MATCHED, 100, 50)], 1, "hourly")
    assert over.bias_mw == 50.0  # over-forecast => positive
    assert under.bias_mw == -50.0  # under-forecast => negative


def test_mape_excludes_zero_actuals_and_reports_exclusion_count():
    points = [
        point(STATUS_MATCHED, actual=0, forecast=10),  # denominator 0 -> excluded
        point(STATUS_MATCHED, actual=100, forecast=150),  # 50%
    ]
    stats = compute_stats(points, expected_count=2, grain="hourly")
    assert stats.mape_pct == 50.0
    assert stats.mape_excluded_intervals == 1
    assert stats.n_matched == 2  # still matched for non-percentage metrics


def test_mape_is_null_when_every_denominator_is_zero():
    stats = compute_stats([point(STATUS_MATCHED, 0, 5)], 1, "hourly")
    assert stats.mape_pct is None
    assert stats.mape_excluded_intervals == 1
    assert stats.mae_mw == 5.0  # absolute metrics still valid


def test_no_matched_intervals_yields_null_metrics_not_zero():
    points = [point(STATUS_ACTUAL_ONLY, actual=100, forecast=None)]
    stats = compute_stats(points, expected_count=1, grain="hourly")
    assert stats.n_matched == 0
    assert stats.coverage_pct == 0.0
    assert stats.coverage_complete is False
    for value in (stats.mae_mw, stats.rmse_mw, stats.bias_mw, stats.mape_pct,
                  stats.avg_actual_mw, stats.avg_forecast_mw):
        assert value is None


def test_coverage_and_missing_counts_are_reported():
    points = [
        point(STATUS_MATCHED, 100, 110),
        point(STATUS_ACTUAL_ONLY, 100, None),
    ]
    stats = compute_stats(points, expected_count=4, grain="hourly")
    assert stats.n_expected == 4
    assert stats.n_matched == 1
    assert stats.n_missing == 3
    assert stats.coverage_pct == 25.0
    assert stats.coverage_complete is False
    assert stats.status_counts["actual_only"] == 1


def test_incomplete_coverage_is_never_flagged_complete():
    points = [point(STATUS_MATCHED, 100, 110)]
    stats = compute_stats(points, expected_count=24, grain="hourly")
    assert stats.coverage_complete is False
    assert stats.coverage_pct < 100.0


def test_averages_use_matched_intervals_only():
    points = [
        point(STATUS_MATCHED, actual=100, forecast=200),
        point(STATUS_ACTUAL_ONLY, actual=9999, forecast=None),
    ]
    stats = compute_stats(points, expected_count=2, grain="hourly")
    assert stats.avg_actual_mw == 100.0
    assert stats.avg_forecast_mw == 200.0


# -- Feature C: reliability additions ---------------------------------------


def test_median_absolute_error_for_odd_and_even_samples():
    odd = compute_stats(
        [point(STATUS_MATCHED, 100, 110), point(STATUS_MATCHED, 100, 120),
         point(STATUS_MATCHED, 100, 160)],  # |err| = 10, 20, 60
        3, "hourly",
    )
    assert odd.median_abs_error_mw == 20.0
    even = compute_stats(
        [point(STATUS_MATCHED, 100, 110), point(STATUS_MATCHED, 100, 120),
         point(STATUS_MATCHED, 100, 150), point(STATUS_MATCHED, 100, 160)],  # 10,20,50,60
        4, "hourly",
    )
    assert even.median_abs_error_mw == 35.0  # (20+50)/2


def test_p90_nearest_rank_requires_ten_matched_intervals():
    # <10 matched -> p90 null (not reported from a thin sample)
    few = compute_stats([point(STATUS_MATCHED, 100, 110)] * 9, 9, "hourly")
    assert few.p90_abs_error_mw is None
    # 10 matched, |err| all 10 except one 1000 -> nearest-rank rank=ceil(9)=9 -> 10
    values = [10] * 9 + [1000]
    points = [
        point(STATUS_MATCHED, 100, 100 + v, hour=i) for i, v in enumerate(values)
    ]
    stats = compute_stats(points, 10, "hourly")
    assert stats.p90_abs_error_mw == 10.0  # 9th smallest of 10
    # and the max sits above p90
    assert max(values) > stats.p90_abs_error_mw
    # 100 matched with |err| = index -> nearest-rank: ceil(0.9*100)=90th smallest -> 90
    points = [point(STATUS_MATCHED, 0, i + 1, hour=i % 24, day=1 + i // 24) for i in range(100)]
    stats = compute_stats(points, 100, "hourly")
    assert stats.p90_abs_error_mw == 90.0


def test_p90_is_null_when_zero_matched():
    stats = compute_stats([], 10, "hourly")
    assert stats.p90_abs_error_mw is None
    assert stats.median_abs_error_mw is None


def test_missing_actual_and_forecast_counts_are_explicit():
    from app.models.records import STATUS_ACTUAL_ONLY, STATUS_FORECAST_ONLY

    points = [
        point(STATUS_MATCHED, 100, 110),
        point(STATUS_FORECAST_ONLY, None, 90),
        point(STATUS_FORECAST_ONLY, None, 95),
        point(STATUS_ACTUAL_ONLY, 100, None),
    ]
    stats = compute_stats(points, expected_count=4, grain="hourly")
    assert stats.n_missing_actual == 2  # forecast_only x2
    assert stats.n_missing_forecast == 1  # actual_only x1
    assert stats.n_matched == 1
    assert stats.n_missing == 3
