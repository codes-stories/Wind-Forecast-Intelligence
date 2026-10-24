"""Endpoint contracts, input validation and upstream failure handling."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import get_store_dep
from app.services.elexon_client import ElexonTransportError
from tests.conftest import loaded_store, synth_period


@pytest.fixture
def client(synth_store):
    app.dependency_overrides[get_store_dep] = lambda: synth_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_reports_cache_state_without_calling_upstream():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["period_start"] == "2026-01-01"
    assert body["period_end"] == "2026-01-31"
    assert body["decision_cutoff_utc"] == "09:20"
    assert body["cache"]["loaded"] is False
    assert body["cache"]["ttl_seconds"] == 3600


def test_openapi_document_is_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in ("/health", "/api/overview", "/api/timeseries", "/api/accuracy",
                 "/api/forecasts/latest"):
        assert path in paths


def test_overview_returns_both_grains_with_coverage(client):
    body = client.get("/api/overview").json()
    assert body["period_start"] == "2026-01-01"
    assert body["decision_cutoff_utc"] == "09:20"
    for grain in ("hourly", "halfhourly"):
        stats = body[grain]
        assert stats["grain"] == grain
        assert stats["coverage_pct"] == 100.0
        assert stats["coverage_complete"] is True
        assert stats["mae_mw"] is not None
        assert stats["n_matched"] == stats["n_expected"]
    assert body["hourly"]["n_expected"] == 31 * 24
    assert body["halfhourly"]["n_expected"] == 31 * 48
    # audit: only pre-cutoff 07:30 vintages were selected
    assert len(body["selected_publish_times"]) == 31
    assert all(p.endswith("T07:30:00Z") for p in body["selected_publish_times"])
    assert body["vintages_fetched"] == 62  # 2 vintages/day x 31 days


def test_timeseries_halfhourly_contract_for_frontend(client):
    response = client.get("/api/timeseries?start=2026-01-15&end=2026-01-15")
    assert response.status_code == 200
    body = response.json()
    assert body["grain"] == "halfhourly"
    rows = body["rows"]
    assert len(rows) == 48
    row = rows[20]  # index 20 -> settlement period 21 (10:00-10:30)
    assert row["timestamp"].startswith("2026-01-15T10:00:00Z")
    assert row["settlement_period"] == 21
    assert row["status"] == "matched"
    assert row["forecast_publish_time"].endswith("T07:30:00Z")
    assert row["error_mw"] == pytest.approx(row["forecast_mw"] - row["actual_mw"])
    # the frontend never sees Elexon's raw field names
    assert "dataset" not in row and "fuelType" not in row and "publishTime" not in row


def test_timeseries_hourly_grain(client):
    body = client.get("/api/timeseries?start=2026-01-15&end=2026-01-15&grain=hourly").json()
    assert body["grain"] == "hourly"
    assert len(body["rows"]) == 24
    assert all(row["settlement_period"] is None for row in body["rows"])


def test_accuracy_reports_sample_size_and_coverage(client):
    body = client.get("/api/accuracy?start=2026-01-10&end=2026-01-12&grain=hourly").json()
    assert body["n_expected"] == 3 * 24
    assert body["n_matched"] == 72
    assert body["n_missing"] == 0
    assert body["coverage_pct"] == 100.0
    assert body["mae_mw"] is not None
    assert body["mape_pct"] is not None
    assert body["mape_excluded_intervals"] == 0
    assert "matched intervals only" in body["note"]


def test_latest_forecast_selects_pre_cutoff_and_lists_ignored(client):
    body = client.get("/api/forecasts/latest?delivery_date=2026-01-15").json()
    assert body["delivery_date"] == "2026-01-15"
    assert body["decision_cutoff_utc"].startswith("2026-01-14T09:20:00Z")
    assert body["selected_publish_time"] == "2026-01-14T07:30:00Z"
    assert body["ignored_post_cutoff_publish_times"] == ["2026-01-14T09:30:00Z"]
    assert body["hours"] == 24
    assert all(row["forecast_mw"] == 9000 + h for h, row in enumerate(body["rows"]))


def test_invalid_date_range_is_rejected(client):
    response = client.get("/api/timeseries?start=2026-01-20&end=2026-01-10")
    assert response.status_code == 400
    assert "on or before" in response.json()["detail"]


def test_range_outside_reporting_period_is_rejected(client):
    response = client.get("/api/accuracy?start=2025-12-01&end=2026-01-10")
    assert response.status_code == 400
    assert "reporting period" in response.json()["detail"]


def test_unparseable_date_is_rejected(client):
    assert client.get("/api/timeseries?start=not-a-date").status_code == 422


def test_latest_forecast_rejects_date_outside_period(client):
    response = client.get("/api/forecasts/latest?delivery_date=2026-02-01")
    assert response.status_code == 400


def test_upstream_failure_surfaces_as_502_with_real_error():
    def failing_dependency():
        raise ElexonTransportError("timeout calling /datasets/FUELHH/stream")

    app.dependency_overrides[get_store_dep] = failing_dependency
    try:
        with TestClient(app) as client:
            response = client.get("/api/overview")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert "timeout calling /datasets/FUELHH/stream" in response.json()["detail"]


def test_refresh_param_forces_reload_of_cache(synth_store):
    actuals, forecasts = synth_period()
    store = loaded_store(actuals, forecasts)
    app.dependency_overrides[get_store_dep] = lambda refresh=False: store
    try:
        with TestClient(app) as client:
            body = client.get("/api/overview?refresh=true").json()
    finally:
        app.dependency_overrides.clear()
    assert body["hourly"]["n_matched"] == 31 * 24


def test_cors_allows_intended_frontend_origins(client):
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.get("/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_other_origins(client):
    response = client.get("/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200  # request itself is served...
    assert "access-control-allow-origin" not in response.headers  # ...but no CORS grant


def test_cors_preflight_for_intended_origin(client):
    response = client.options(
        "/api/accuracy",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_cors_preflight_denied_for_other_origin(client):
    response = client.options(
        "/api/accuracy",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
