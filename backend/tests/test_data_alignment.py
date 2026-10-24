"""Deduplication, forecast/actual alignment and grain mapping."""
from datetime import date, timezone

from tests.conftest import dt, make_actual, make_forecast, loaded_store
from app.models.records import STATUS_ACTUAL_ONLY, STATUS_FORECAST_ONLY, STATUS_MATCHED
from app.services.forecast_service import (
    build_halfhourly_points,
    build_hourly_points,
    dedupe_actuals,
    dedupe_forecasts,
)

UTC = timezone.utc
DAY = date(2026, 1, 15)


def test_duplicate_actual_intervals_keep_latest_restatement():
    older = make_actual(DAY, 5, 7000, publish=dt(15, 2, 30))
    newer = make_actual(DAY, 5, 7100, publish=dt(16, 0, 0))  # restated value
    kept, dropped = dedupe_actuals([older, newer])
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0].generation_mw == 7100
    assert kept[0].publish_time == dt(16, 0, 0)


def test_duplicate_forecast_rows_are_dropped():
    a = make_forecast(dt(14, 7, 30), dt(15, 10), 5000)
    b = make_forecast(dt(14, 7, 30), dt(15, 10), 5000)
    kept, dropped = dedupe_forecasts([a, b])
    assert dropped == 1
    assert len(kept) == 1


def test_distinct_settlement_periods_are_not_deduplicated():
    rows = [make_actual(DAY, sp, 5000) for sp in range(1, 49)]
    kept, dropped = dedupe_actuals(rows)
    assert len(kept) == 48
    assert dropped == 0


def test_hourly_join_requires_both_half_hours():
    forecast = make_forecast(dt(14, 7, 30), dt(15, 10), 8000)
    left_only = make_actual(DAY, 21, 7000)  # 10:00-10:30 only
    points = build_hourly_points(DAY, DAY, {left_only.start_time: left_only},
                                 {forecast.start_time: forecast})
    assert len(points) == 24
    hour10 = next(p for p in points if p.timestamp == dt(15, 10))
    assert hour10.actual_mw is None  # partial actual is never silently averaged
    assert hour10.status == STATUS_FORECAST_ONLY


def test_hourly_actual_averages_the_two_half_hours():
    left = make_actual(DAY, 21, 7000)  # 10:00
    right = make_actual(DAY, 22, 9000)  # 10:30
    forecast = make_forecast(dt(14, 7, 30), dt(15, 10), 8500)
    points = build_hourly_points(DAY, DAY,
                                 {left.start_time: left, right.start_time: right},
                                 {forecast.start_time: forecast})
    hour10 = next(p for p in points if p.timestamp == dt(15, 10))
    assert hour10.actual_mw == 8000.0
    assert hour10.forecast_mw == 8500
    assert hour10.status == STATUS_MATCHED
    assert hour10.error_mw == 500.0
    assert hour10.forecast_publish_time == dt(14, 7, 30)


def test_actual_only_and_missing_both_classification():
    left = make_actual(DAY, 1, 6000)  # 00:00-00:30
    right = make_actual(DAY, 2, 6100)  # 00:30-01:00 -> hour 00:00 complete
    points = build_hourly_points(DAY, DAY,
                                 {left.start_time: left, right.start_time: right}, {})
    hour0 = points[0]
    assert hour0.actual_mw == 6050.0
    assert hour0.status == STATUS_ACTUAL_ONLY  # no forecast for this hour
    hour1 = points[1]  # no actual, no forecast
    assert hour1.status == "missing_both"
    assert hour1.actual_mw is None and hour1.forecast_mw is None


def test_halfhourly_mapping_applies_hourly_forecast_to_both_half_hours():
    forecast = make_forecast(dt(14, 7, 30), dt(15, 10), 8000)
    left = make_actual(DAY, 21, 7000)
    right = make_actual(DAY, 22, 9000)
    points = build_halfhourly_points(
        DAY, DAY,
        {left.start_time: left, right.start_time: right},
        {forecast.start_time: forecast},
    )
    assert len(points) == 48
    sp21 = next(p for p in points if p.settlement_period == 21)
    sp22 = next(p for p in points if p.settlement_period == 22)
    assert sp21.forecast_mw == 8000 and sp22.forecast_mw == 8000  # documented mapping
    assert sp21.actual_mw == 7000 and sp22.actual_mw == 9000
    assert sp21.status == sp22.status == STATUS_MATCHED


def test_null_forecast_value_is_not_matched():
    forecast = make_forecast(dt(14, 7, 30), dt(15, 10), None)
    left = make_actual(DAY, 21, 7000)
    right = make_actual(DAY, 22, 7000)
    points = build_hourly_points(DAY, DAY,
                                 {left.start_time: left, right.start_time: right},
                                 {forecast.start_time: forecast})
    hour10 = next(p for p in points if p.timestamp == dt(15, 10))
    assert hour10.forecast_mw is None
    assert hour10.status == STATUS_ACTUAL_ONLY


def test_store_load_computes_stats_and_period_shapes():
    store = loaded_store()
    assert store.stats["actual_rows_fetched"] == 0
    assert len(store.hourly) == 31 * 24
    assert len(store.halfhourly) == 31 * 48
    assert store.is_loaded


def test_alignment_joins_on_delivery_timestamp_not_publish_time():
    """A forecast for 10:00 must not attach to 11:00 even though publish times differ."""
    forecast = make_forecast(dt(14, 7, 30), dt(15, 10), 8000)
    left = make_actual(DAY, 23, 7777)  # 11:00-11:30
    right = make_actual(DAY, 24, 7779)  # 11:30-12:00 -> hour 11:00 complete
    points = build_hourly_points(DAY, DAY,
                                 {left.start_time: left, right.start_time: right},
                                 {forecast.start_time: forecast})
    hour10 = next(p for p in points if p.timestamp == dt(15, 10))
    hour11 = next(p for p in points if p.timestamp == dt(15, 11))
    assert hour10.forecast_mw == 8000 and hour10.actual_mw is None
    assert hour11.forecast_mw is None and hour11.actual_mw == 7778.0
