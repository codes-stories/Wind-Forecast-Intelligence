"""Decision Lab endpoints: cutoff sensitivity, calibration, skill vs persistence."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.routes import get_store_dep
from app.main import app
from tests.conftest import loaded_store, make_forecast, make_actual, synth_period

UTC = timezone.utc


def with_store(store):
    app.dependency_overrides[get_store_dep] = lambda: store
    return TestClient(app)


def clear():
    app.dependency_overrides.clear()


# -- cutoff sensitivity ------------------------------------------------------


def test_cutoff_sensitivity_candidates_cover_the_gate_decisions(synth_store):
    client = with_store(synth_store)
    try:
        body = client.get(
            "/api/forecasts/cutoff-sensitivity?start=2026-01-01&end=2026-01-31"
        ).json()
    finally:
        clear()
    labels = [c["cutoff_utc"] for c in body["candidates"]]
    assert labels == ["07:30", "09:20", "09:30"]  # sorted, configured included
    assert body["current_cutoff_utc"] == "09:20"
    current = next(c for c in body["candidates"] if c["is_current"])
    assert current["cutoff_utc"] == "09:20"
    assert current["delta_mae_mw"] == 0.0  # the current gate vs itself
    assert sum(1 for c in body["candidates"] if c["is_current"]) == 1

    # synthetic post-cutoff vintage (9500+h) is closer to actual (10000+sp)
    # than the eligible vintage (9000+h) -> the later gate scores better here
    later = next(c for c in body["candidates"] if c["cutoff_utc"] == "09:30")
    assert later["mae_mw"] is not None and current["mae_mw"] is not None
    assert later["delta_mae_mw"] < 0
    assert body["best_cutoff_utc"] == "09:30"
    assert body["best_delta_mae_mw"] < 0
    for candidate in body["candidates"]:
        assert candidate["n_matched"] == 31 * 24
        assert candidate["coverage_pct"] == 100.0
        assert candidate["rmse_mw"] >= candidate["mae_mw"]
    assert "what-if" in body["note"] or "what-if" in body["rule"].lower()
    assert body["limitation"] is None


def test_cutoff_sensitivity_rejects_bad_ranges(synth_store):
    client = with_store(synth_store)
    try:
        assert client.get(
            "/api/forecasts/cutoff-sensitivity?start=2026-02-01&end=2026-02-05"
        ).status_code == 400
        assert client.get(
            "/api/forecasts/cutoff-sensitivity?start=2026-01-20&end=2026-01-10"
        ).status_code == 400
    finally:
        clear()


def test_cutoff_sensitivity_without_forecasts_reports_limitation():
    store = loaded_store(actuals=synth_period()[0], forecasts=[])  # actuals only
    client = with_store(store)
    try:
        body = client.get(
            "/api/forecasts/cutoff-sensitivity?start=2026-01-01&end=2026-01-31"
        ).json()
    finally:
        clear()
    assert body["candidates"] == []
    assert body["best_cutoff_utc"] is None
    assert body["limitation"] is not None and "WINDFOR" in body["limitation"]


# -- calibration -------------------------------------------------------------


def test_calibration_counts_actuals_against_vintage_envelope(synth_store):
    client = with_store(synth_store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-01&end=2026-01-31").json()
    finally:
        clear()
    cal = body["calibration"]
    # synth: one eligible vintage per hour (07:30, 9000+h) and actuals above it
    assert cal["hours_total"] == 31 * 24
    assert cal["hours_evaluated"] == 31 * 24
    assert cal["hours_above"] == 31 * 24  # actual always above the envelope
    assert cal["hours_inside"] == 0
    assert cal["hours_below"] == 0
    assert cal["inside_pct"] == 0.0
    assert cal["avg_vintages_per_hour"] == 1.0  # single eligible vintage -> zero width
    assert cal["avg_envelope_width_mw"] == 0.0
    assert "consensus proxy" in cal["limitation"]


def test_calibration_is_never_presented_as_calibrated(synth_store):
    client = with_store(synth_store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-15&end=2026-01-15").json()
    finally:
        clear()
    assert "not a calibrated probabilistic forecast" in body["calibration"]["limitation"]


# -- skill vs persistence ----------------------------------------------------


def test_skill_on_synthetic_data_excludes_day_one_and_never_fakes_zero_skill(
    synth_store,
):
    """Synth actuals repeat every day -> persistence is perfect and the skill
    ratio is undefined; it must be null, never 0 (which would claim parity)."""
    client = with_store(synth_store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-01&end=2026-01-31").json()
    finally:
        clear()
    skill = body["skill"]
    assert skill["grain"] == "halfhourly"
    assert skill["n_matched"] == 31 * 48
    assert skill["n_persistence_unavailable"] == 48  # 1 Jan has no prior day
    assert skill["n_evaluated"] == 31 * 48 - 48
    assert skill["persistence_mae_mw"] == 0.0  # identical daily actuals
    assert skill["windfor_mae_mw"] is not None and skill["windfor_mae_mw"] > 0
    assert skill["skill_pct"] is None  # division by a zero baseline is undefined
    assert "T - 24h" in skill["note"]


def test_skill_is_positive_when_forecast_beats_persistence():
    """Day-varying actuals: forecast = actual + 50, persistence = actual - 100
    -> windfor MAE 50 vs persistence MAE 100 -> skill = 50%."""
    actuals = []
    forecasts = []
    day = date(2026, 1, 1)
    while day <= date(2026, 1, 31):
        for hour in range(24):
            value = 5000.0 + 100.0 * day.day + 10.0 * hour
            for sp in (hour * 2 + 1, hour * 2 + 2):
                actuals.append(make_actual(day, sp, value))
            ts = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            publish = (ts - timedelta(days=1)).replace(hour=7, minute=30)  # D-1 07:30, eligible
            forecasts.append(make_forecast(publish, ts, value + 50.0))
        day += timedelta(days=1)
    store = loaded_store(actuals, forecasts)
    client = with_store(store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-01&end=2026-01-31").json()
    finally:
        clear()
    skill = body["skill"]
    assert skill["n_evaluated"] == 31 * 48 - 48
    assert skill["n_persistence_unavailable"] == 48
    assert skill["windfor_mae_mw"] == 50.0
    assert skill["persistence_mae_mw"] == 100.0
    assert skill["skill_pct"] == 50.0  # 100 * (1 - 50/100)


def test_benchmarks_combine_calibration_and_skill_with_ranges(synth_store):
    client = with_store(synth_store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-10&end=2026-01-12").json()
    finally:
        clear()
    assert body["start"] == "2026-01-10"
    assert body["end"] == "2026-01-12"
    assert body["current_cutoff_utc"] == "09:20"
    assert body["calibration"]["hours_total"] == 3 * 24
    assert body["skill"]["n_matched"] == 3 * 48
    assert "historical statistics" in body["note"]


def test_benchmarks_without_forecasts_report_unavailability():
    store = loaded_store(actuals=synth_period()[0], forecasts=[])
    client = with_store(store)
    try:
        body = client.get("/api/benchmarks?start=2026-01-01&end=2026-01-31").json()
    finally:
        clear()
    assert body["calibration"]["hours_evaluated"] == 0
    assert body["calibration"]["inside_pct"] is None  # null, never 0
    assert body["skill"]["n_matched"] == 0
    assert body["skill"]["skill_pct"] is None
    assert "there is no forecast to benchmark" in body["note"]
