"""HTTP error, timeout, malformed response and field validation handling."""
from datetime import date, datetime, timezone

import httpx
import pytest

from app.services.elexon_client import (
    ElexonClient,
    ElexonHTTPError,
    ElexonSchemaError,
    ElexonTransportError,
)
from tests.conftest import make_settings

UTC = timezone.utc


def client(handler, **settings_overrides) -> ElexonClient:
    transport = httpx.MockTransport(handler)
    return ElexonClient(make_settings(**settings_overrides), transport=transport)


def ok(rows):
    return httpx.Response(200, json=rows)


def test_actuals_parse_and_keep_only_wind():
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
            "fuelType": "GAS",
            "generation": 12345,
        },
    ]
    got = client(lambda request: ok(rows)).fetch_actuals(date(2026, 1, 15), date(2026, 1, 15))
    assert len(got) == 1
    row = got[0]
    assert row.generation_mw == 8000.0
    assert row.settlement_period == 21
    assert row.publish_time == datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
    assert row.start_time.tzinfo is not None  # timestamps normalised to aware UTC


def test_actuals_filter_params_are_settlement_based():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(dict(request.url.params))
        return ok([])

    client(handler).fetch_actuals(date(2026, 1, 1), date(2026, 1, 31))
    assert seen["settlementDateFrom"] == "2026-01-01"
    assert seen["settlementDateTo"] == "2026-01-31"
    assert seen["fuelType"] == "WIND"
    assert "publishDateTimeFrom" not in seen  # verified: filters are mutually exclusive


def test_forecast_filter_params_are_publish_based():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(dict(request.url.params))
        return ok([])

    client(handler).fetch_forecasts(
        datetime(2025, 12, 31, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
    )
    assert seen["publishDateTimeFrom"] == "2025-12-31T00:00:00Z"
    assert seen["publishDateTimeTo"] == "2026-01-31T00:00:00Z"


def test_missing_required_field_raises_schema_error():
    bad = [{"dataset": "WINDFOR", "publishTime": "2026-01-14T07:30:00Z"}]  # no startTime
    c = client(lambda request: ok(bad))
    with pytest.raises(ElexonSchemaError):
        c.fetch_forecasts(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))


def test_invalid_timestamp_raises_schema_error():
    bad = [{"dataset": "WINDFOR", "publishTime": "yesterday", "startTime": "2026-01-15T10:00:00Z",
            "generation": 1}]
    c = client(lambda request: ok(bad))
    with pytest.raises(ElexonSchemaError):
        c.fetch_forecasts(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))


def test_non_array_response_raises_schema_error():
    c = client(lambda request: httpx.Response(200, json={"data": []}))
    with pytest.raises(ElexonSchemaError):
        c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))


def test_invalid_json_body_raises_schema_error():
    c = client(lambda request: httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(ElexonSchemaError):
        c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))


def test_client_error_400_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        return httpx.Response(400, json={"errors": {"": "bad request"}})

    c = client(handler, http_retries=3)
    with pytest.raises(ElexonHTTPError) as exc:
        c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))
    assert exc.value.status_code == 400
    assert calls["n"] == 1


def test_server_error_is_retried_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    c = client(handler, http_retries=3)
    with pytest.raises(ElexonHTTPError) as exc:
        c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))
    assert exc.value.status_code == 500
    assert calls["n"] == 3


def test_timeout_raises_transport_error_after_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        raise httpx.TimeoutException("timed out")

    c = client(handler, http_retries=2)
    with pytest.raises(ElexonTransportError):
        c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))
    assert calls["n"] == 2


def test_rate_limit_429_is_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, text="slow down")
        return ok([])

    c = client(handler, http_retries=3)
    rows = c.fetch_actuals(date(2026, 1, 1), date(2026, 1, 2))
    assert rows == []
    assert calls["n"] == 3
