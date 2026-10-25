"""Indicative £ valuation of forecast error (day-ahead market-index price)."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi.testclient import TestClient

from app.api.routes import get_store_dep
from app.main import app
from app.models.records import IntervalPoint, STATUS_MATCHED
from app.services.elexon_client import ElexonTransportError
from app.services.metrics_service import compute_stats
from tests.conftest import FakeClient, dt, loaded_store, make_price, make_settings, synth_period


def matched_point(error, price=None, sp=None, day=15, hour=0):
    """Matched interval with a controlled error, price and grain."""
    minute = 0 if sp is None else 30 * (sp - 1)
    return IntervalPoint(
        timestamp=dt(day, hour, minute),
        settlement_date=date(2026, 1, day),
        settlement_period=sp,
        actual_mw=100.0,
        forecast_mw=100.0 + error,
        status=STATUS_MATCHED,
        forecast_publish_time=dt(14, 7, 30),
        price_gbp_per_mwh=price,
    )


# -- unit level: compute_stats cost block -----------------------------------


def test_cost_sums_error_times_price_times_hours():
    points = [
        matched_point(+20, price=50.0),   # hourly: 20 x 50 x 1h = 1000
        matched_point(-30, price=100.0),  # -30 x 100 x 1h = -3000
    ]
    stats = compute_stats(points, 2, "hourly")
    assert stats.n_priced_intervals == 2
    assert stats.net_error_value_gbp == -2000.0
    assert stats.abs_error_value_gbp == 4000.0
    assert stats.price_coverage_pct == 100.0
    assert stats.price_source is not None and "APXMIDP" in stats.price_source


def test_cost_uses_half_hour_duration_at_halfhourly_grain():
    stats = compute_stats([matched_point(+20, price=50.0, sp=1)], 1, "halfhourly")
    assert stats.abs_error_value_gbp == 500.0  # 20 x 50 x 0.5h


def test_cost_is_null_never_zero_without_prices():
    stats = compute_stats([matched_point(+20)], 1, "hourly")
    assert stats.n_priced_intervals == 0
    assert stats.price_coverage_pct == 0.0
    assert stats.net_error_value_gbp is None
    assert stats.abs_error_value_gbp is None
    assert stats.price_source is None


def test_price_coverage_reports_partial_pricing():
    stats = compute_stats([matched_point(+20, price=50.0), matched_point(+20)], 2, "hourly")
    assert stats.n_priced_intervals == 1
    assert stats.price_coverage_pct == 50.0
    assert stats.abs_error_value_gbp == 1000.0  # only the priced interval counts


def test_cost_is_null_when_no_matched_intervals():
    stats = compute_stats([], 10, "hourly")
    assert stats.n_priced_intervals == 0
    assert stats.abs_error_value_gbp is None


# -- integration: store -> endpoints ----------------------------------------


def day_prices(day: int, price: float = 100.0):
    return [make_price(date(2026, 1, day), sp, price) for sp in range(1, 49)]


def test_accuracy_reports_hand_verifiable_pound_totals():
    store = loaded_store(*synth_period(), prices=day_prices(15))
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get(
                "/api/accuracy?start=2026-01-15&end=2026-01-15&grain=halfhourly"
            ).json()
    finally:
        app.dependency_overrides.clear()
    # synth: error on half-hour (h, sp) = (9000+h) - (10000+sp); price flat 100
    # |error| sum over 48 intervals x 100 GBP/MWh x 0.5h = 2,431,200
    assert body["n_priced_intervals"] == 48
    assert body["price_coverage_pct"] == 100.0
    assert body["abs_error_value_gbp"] == 2431200.0
    assert body["net_error_value_gbp"] == -2431200.0  # under-forecast everywhere
    assert "market-index" in body["note"]


def test_accuracy_note_says_pounds_unavailable_when_feed_is_empty():
    store = loaded_store(*synth_period())  # no prices
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get(
                "/api/accuracy?start=2026-01-15&end=2026-01-15&grain=hourly"
            ).json()
    finally:
        app.dependency_overrides.clear()
    assert body["abs_error_value_gbp"] is None
    assert body["n_priced_intervals"] == 0
    assert "unavailable" in body["note"]


def test_timeseries_rows_carry_price_and_error_value():
    store = loaded_store(*synth_period(), prices=day_prices(15))
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            rows = client.get(
                "/api/timeseries?start=2026-01-15&end=2026-01-15&grain=halfhourly"
            ).json()["rows"]
    finally:
        app.dependency_overrides.clear()
    first = rows[0]  # forecast 9000, actual 10001 -> error -1001, price 100, 0.5h
    assert first["price_gbp_per_mwh"] == 100.0
    assert first["error_value_gbp"] == -1001.0 * 100.0 * 0.5


def test_csv_carries_price_and_value_columns_when_priced():
    store = loaded_store(*synth_period(), prices=day_prices(15))
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/export.csv?start=2026-01-15&end=2026-01-15&grain=hourly"
            )
    finally:
        app.dependency_overrides.clear()
    rows = list(csv.reader(io.StringIO(resp.text)))
    header, first = rows[0], rows[1]
    assert header[-2:] == ["day_ahead_price_gbp_per_mwh", "error_value_gbp"]
    assert float(first[-2]) == 100.0  # hourly price = mean of the two half-hours
    assert float(first[-1]) == -1001.5 * 100.0  # error x price x 1h


# -- degradation paths -------------------------------------------------------


def test_price_feed_failure_degrades_to_null_pounds_not_an_error():
    from app.services.forecast_service import DataStore

    class PriceFailingClient(FakeClient):
        def fetch_prices(self, start, end):
            raise ElexonTransportError("price endpoint down")

    actuals, forecasts = synth_period()
    store = DataStore(PriceFailingClient(actuals, forecasts), make_settings())
    store.load()  # must not raise
    assert store.prices == {}
    assert store.stats["price_points_fetched"] == 0
    assert store.halfhourly[0].price_gbp_per_mwh is None


def test_prices_disabled_skips_the_price_feed():
    from app.services.forecast_service import DataStore

    actuals, forecasts = synth_period()
    client = FakeClient(actuals, forecasts, prices=day_prices(15))
    store = DataStore(client, make_settings(prices_enabled=False))
    store.load()
    assert client.price_calls == 0
    assert store.prices == {}
