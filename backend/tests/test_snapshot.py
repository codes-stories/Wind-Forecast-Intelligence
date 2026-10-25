"""Cold-start snapshot: encode/decode round-trip, validation, load order."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services import forecast_service, snapshot_service
from app.services.forecast_service import DataStore, get_store, reset_cache
from app.services.elexon_client import ElexonTransportError
from tests.conftest import FakeClient, loaded_store, make_price, make_settings, synth_period

UTC = timezone.utc


@pytest.fixture(autouse=True)
def clean_cache():
    reset_cache()
    yield
    reset_cache()


def priced_store():
    actuals, forecasts = synth_period()
    prices = [make_price(date(2026, 1, 15), sp, 100.0) for sp in range(1, 49)]
    return loaded_store(actuals, forecasts, prices=prices), actuals, forecasts, prices


def test_encode_decode_roundtrip_preserves_every_row(tmp_path):
    store, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json.gz"))
    payload = snapshot_service.encode(actuals, forecasts, prices, settings)
    assert payload["version"] == snapshot_service.SNAPSHOT_VERSION
    assert payload["fuel_type"] == "WIND"

    got_actuals, got_forecasts, got_prices = snapshot_service.decode(payload)
    assert len(got_actuals) == len(actuals)
    assert len(got_forecasts) == len(forecasts)
    assert got_prices == {(p.settlement_date, p.settlement_period): p.price_gbp_per_mwh for p in prices}
    first = next(r for r in got_actuals if r.settlement_period == 1 and r.settlement_date == date(2026, 1, 1))
    assert first.start_time == datetime(2026, 1, 1, 0, tzinfo=UTC)
    assert first.generation_mw == 10001.0
    assert got_forecasts[0].publish_time.tzinfo is not None  # still aware UTC


def test_snapshot_build_and_load_produces_identical_series(tmp_path):
    _, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json.gz"))
    payload = snapshot_service.encode(actuals, forecasts, prices, settings)
    assert snapshot_service.save(payload, settings) is not None

    loaded = snapshot_service.load(settings)
    assert loaded is not None
    store = DataStore(FakeClient(), settings)  # any client works: no fetch happens
    store.load_snapshot(loaded)
    assert store.stats["source"].startswith("shipped snapshot")
    assert "generated" in store.stats["source"]

    live = loaded_store(actuals, forecasts, prices=prices)
    assert len(store.hourly) == len(live.hourly)
    assert len(store.halfhourly) == len(live.halfhourly)
    for snap_pt, live_pt in zip(store.halfhourly, live.halfhourly):
        assert snap_pt.timestamp == live_pt.timestamp
        assert snap_pt.actual_mw == live_pt.actual_mw
        assert snap_pt.forecast_mw == live_pt.forecast_mw
        assert snap_pt.price_gbp_per_mwh == live_pt.price_gbp_per_mwh
    assert store.stats["actual_rows_fetched"] == len(actuals)
    assert store.stats["forecast_rows_fetched"] == len(forecasts)
    assert store.stats["price_points_fetched"] == len(prices)


def test_load_rejects_missing_mismatched_or_disabled_snapshots(tmp_path):
    missing = make_settings(snapshot_path=str(tmp_path / "nope.json.gz"))
    assert snapshot_service.load(missing) is None

    _, actuals, forecasts, prices = priced_store()
    path = str(tmp_path / "snap.json.gz")
    good = make_settings(snapshot_path=path)
    snapshot_service.save(snapshot_service.encode(actuals, forecasts, prices, good), good)

    wrong_period = make_settings(snapshot_path=path, period_end=date(2026, 2, 28))
    assert snapshot_service.load(wrong_period) is None
    wrong_fuel = make_settings(snapshot_path=path, fuel_type="NUCLEAR")
    assert snapshot_service.load(wrong_fuel) is None
    disabled = make_settings(snapshot_path=path, snapshot_enabled=False)
    assert snapshot_service.load(disabled) is None

    corrupt = make_settings(snapshot_path=path)
    with open(path, "wb") as handle:  # overwrite the gzip with junk
        handle.write(b"not a gzip file")
    assert snapshot_service.load(corrupt) is None


def test_plain_json_snapshot_is_supported(tmp_path):
    _, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json"))  # no .gz
    snapshot_service.save(snapshot_service.encode(actuals, forecasts, prices, settings), settings)
    assert snapshot_service.load(settings) is not None


class BrokenClient(FakeClient):
    """Any live fetch would explode: proves which load path was taken."""

    def fetch_actuals(self, start, end, fuel_type=None):
        raise ElexonTransportError("upstream must not be called")


def _broken_builder(s, fuel=None):
    return DataStore(BrokenClient(), s, fuel)


def test_get_store_serves_the_snapshot_on_cold_start_without_the_upstream(
    tmp_path, monkeypatch
):
    _, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json.gz"))
    snapshot_service.save(snapshot_service.encode(actuals, forecasts, prices, settings), settings)

    monkeypatch.setattr(forecast_service, "build_store", _broken_builder)
    store = get_store(settings)  # cold start, refresh=False
    assert store.is_loaded
    assert store.stats["source"].startswith("shipped snapshot")
    assert len(store.hourly) == 31 * 24


def test_refresh_bypasses_the_snapshot_and_forces_a_live_fetch(
    tmp_path, monkeypatch
):
    _, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json.gz"))
    snapshot_service.save(snapshot_service.encode(actuals, forecasts, prices, settings), settings)

    monkeypatch.setattr(forecast_service, "build_store", _broken_builder)
    with pytest.raises(ElexonTransportError):
        get_store(settings, refresh=True)


def test_cache_status_reports_the_dataset_source(tmp_path, monkeypatch):
    _, actuals, forecasts, prices = priced_store()
    settings = make_settings(snapshot_path=str(tmp_path / "snap.json.gz"))
    snapshot_service.save(snapshot_service.encode(actuals, forecasts, prices, settings), settings)

    monkeypatch.setattr(
        forecast_service,
        "build_store",
        lambda s, fuel=None: DataStore(FakeClient(), s, fuel),
    )
    store = get_store(settings)
    status = forecast_service.cache_status(settings)
    assert store.stats["source"].startswith("shipped snapshot")
    assert status["source"].startswith("shipped snapshot")


def test_live_load_is_labelled_as_such(tmp_path, monkeypatch):
    """No snapshot file -> live fetch path, source labelled 'live fetch'."""
    settings = make_settings(snapshot_path=str(tmp_path / "missing.json.gz"))
    monkeypatch.setattr(
        forecast_service,
        "build_store",
        lambda s, fuel=None: DataStore(FakeClient(), s, fuel),
    )
    store = get_store(settings)
    assert store.stats["source"] == "live fetch"
