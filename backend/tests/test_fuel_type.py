"""FUELHH fuelType filter: config default, per-request override, store isolation."""
from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import routes
from app.api.routes import get_store_dep
from app.core.config import FUEL_TYPES, Settings, normalize_fuel_type
from app.main import app
from app.services import forecast_service
from app.services.elexon_client import ElexonClient
from app.services.forecast_service import DataStore
from tests.conftest import FakeClient, loaded_store, make_settings, synth_period


# -- config ------------------------------------------------------------------


def test_default_fuel_type_is_wind():
    assert make_settings().fuel_type == "WIND"


def test_normalize_fuel_type_accepts_any_case():
    assert normalize_fuel_type("nuclear") == "NUCLEAR"
    assert normalize_fuel_type(" Wind ") == "WIND"


@pytest.mark.parametrize("bad", ["", "SOLAR", "WIND POWER", "WIND;DROP"])
def test_normalize_fuel_type_rejects_unknown_values(bad):
    with pytest.raises(ValueError) as exc:
        normalize_fuel_type(bad)
    assert "unknown fuel type" in str(exc.value)


def test_every_documented_fuel_type_is_accepted():
    for fuel in FUEL_TYPES:
        assert normalize_fuel_type(fuel.lower()) == fuel


# -- client ------------------------------------------------------------------


def _client(handler, **overrides) -> ElexonClient:
    return ElexonClient(make_settings(**overrides), transport=httpx.MockTransport(handler))


def test_fuel_type_comes_from_settings_by_default():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    _client(handler, fuel_type="NUCLEAR").fetch_actuals(
        date(2026, 1, 1), date(2026, 1, 31)
    )
    assert seen["fuelType"] == "NUCLEAR"


def test_fuel_type_argument_overrides_settings():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    _client(handler).fetch_actuals(
        date(2026, 1, 1),
        date(2026, 1, 31),
        fuel_type="ccgt",
    )
    assert seen["fuelType"] == "CCGT"
    assert "publishDateTimeFrom" not in seen  # settlement filters stay mutually exclusive


def test_rows_are_filtered_to_the_requested_fuel():
    rows = [
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-15T10:30:00Z",
            "startTime": "2026-01-15T10:00:00Z",
            "settlementDate": "2026-01-15",
            "settlementPeriod": 21,
            "fuelType": "WIND",
            "generation": 8000,
        },
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-15T10:30:00Z",
            "startTime": "2026-01-15T10:00:00Z",
            "settlementDate": "2026-01-15",
            "settlementPeriod": 21,
            "fuelType": "NUCLEAR",
            "generation": 4000,
        },
    ]
    client = _client(lambda request: httpx.Response(200, json=rows))
    got = client.fetch_actuals(
        date(2026, 1, 15),
        date(2026, 1, 15),
        fuel_type="NUCLEAR",
    )
    assert [r.generation_mw for r in got] == [4000.0]


def test_unknown_fuel_type_never_reaches_the_network():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        return httpx.Response(200, json=[])

    with pytest.raises(ValueError):
        _client(handler).fetch_actuals(
            date(2026, 1, 1),
            date(2026, 1, 31),
            fuel_type="SOLAR",
        )
    assert calls["n"] == 0


# -- store -------------------------------------------------------------------


def test_non_wind_store_loads_actuals_but_no_forecast():
    actuals, forecasts = synth_period()
    store = loaded_store(actuals, forecasts, fuel_type="NUCLEAR")

    assert store.fuel_type == "NUCLEAR"
    assert store.forecast_available is False
    assert store.forecast_rows == []
    assert store.selected == {}
    assert store.client.requested_fuel_types == ["NUCLEAR"]
    assert store.client.forecast_calls == 0
    assert store.stats["fuel_type"] == "NUCLEAR"
    assert store.stats["forecast_available"] is False
    assert store.halfhourly
    assert all(p.status == "actual_only" for p in store.halfhourly)


def test_wind_store_still_builds_forecast_comparison():
    actuals, forecasts = synth_period()
    store = loaded_store(actuals, forecasts)
    assert store.forecast_available is True
    assert store.client.forecast_calls == 1
    assert all(p.status == "matched" for p in store.halfhourly)


def test_cache_keeps_one_store_per_fuel_type(monkeypatch):
    built: list[str | None] = []

    def fake_build(settings: Settings, fuel_type: str | None = None):
        built.append(fuel_type)
        return DataStore(FakeClient(), settings, fuel_type)

    monkeypatch.setattr(forecast_service, "build_store", fake_build)
    settings = make_settings()
    forecast_service.reset_cache()
    try:
        wind = forecast_service.get_store(settings)
        nuclear = forecast_service.get_store(settings, fuel_type="NUCLEAR")
        again_wind = forecast_service.get_store(settings, fuel_type="wind")
        assert wind is not nuclear
        assert wind is again_wind  # same fuel, same store
        assert built == ["WIND", "NUCLEAR"]
    finally:
        forecast_service.reset_cache()


# -- HTTP layer --------------------------------------------------------------


def test_fuel_type_query_param_is_validated():
    assert routes._fuel_type(None, make_settings()) == "WIND"
    assert routes._fuel_type("nuclear", make_settings()) == "NUCLEAR"
    with pytest.raises(HTTPException) as exc:
        routes._fuel_type("SOLAR", make_settings())
    assert exc.value.status_code == 400
    assert "unknown fuel type" in exc.value.detail


def test_health_reports_the_fuel_filter_in_effect():
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["fuel_type"] == "WIND"


def test_data_quality_describes_a_non_wind_dataset():
    actuals, _ = synth_period()
    store = loaded_store(actuals, fuel_type="NUCLEAR")
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get("/api/data-quality").json()
    finally:
        app.dependency_overrides.clear()

    assert body["fuel_type"] == "NUCLEAR"
    assert body["forecast_available"] is False
    assert body["sources"]["actual"] == "Elexon FUELHH (nuclear, half-hourly)"
    assert "wind-only" in body["sources"]["forecast"]
    assert body["quality_status"] == "incomplete"
    assert any("WINDFOR publishes wind only" in item for item in body["limitations"])
