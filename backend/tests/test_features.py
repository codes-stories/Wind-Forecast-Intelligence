"""Feature A/D/E/F endpoints: vintage explorer, data quality, insights, CSV export."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_store_dep
from app.main import app
from tests.conftest import loaded_store, synth_period


@pytest.fixture
def client(synth_store):
    app.dependency_overrides[get_store_dep] = lambda: synth_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# -- Feature A ---------------------------------------------------------------


def test_vintages_endpoint_lists_eligible_and_post_cutoff(client):
    # period 21 on 2026-01-15 -> clock hour 10:00 UTC
    response = client.get("/api/forecasts/vintages?date=2026-01-15&period=21")
    assert response.status_code == 200
    body = response.json()
    assert body["delivery_timestamp"].startswith("2026-01-15T10:00:00Z")
    assert body["cutoff_utc"] == "2026-01-14T09:20:00Z"

    assert len(body["vintages"]) == 2  # eligible 07:30 + post-cutoff 09:30
    first, second = body["vintages"]
    assert first["publish_time"].startswith("2026-01-14T07:30:00Z")
    assert first["eligible_at_cutoff"] is True
    assert first["selected"] is True
    assert first["change_mw"] is None  # earliest publication has no delta
    assert second["publish_time"].startswith("2026-01-14T09:30:00Z")
    assert second["eligible_at_cutoff"] is False  # after the 09:20 cutoff
    assert second["selected"] is False
    assert second["change_mw"] == 500.0  # 9510 - 9010 (synthetic data)

    assert body["eligible_count"] == 1
    assert body["post_cutoff_count"] == 1
    # latest available publication is post-cutoff and must stay distinct from selected
    assert body["latest_publish_time"].startswith("2026-01-14T09:30:00Z")
    assert body["latest_forecast_mw"] == 9510.0
    assert body["selected_publish_time"].startswith("2026-01-14T07:30:00Z")
    assert body["selected_forecast_mw"] == 9010.0
    assert body["limitation"] is None

    # error = selected forecast - actual (synthetic actual at period 21 = 10021)
    assert body["actual_mw"] == 10021.0
    assert body["error_mw"] == -1011.0  # 9010 - 10021
    assert body["absolute_error_mw"] == 1011.0


def test_vintages_rejects_out_of_period_and_bad_period(client):
    assert client.get("/api/forecasts/vintages?date=2025-12-31&period=1").status_code == 400
    assert client.get("/api/forecasts/vintages?date=2026-02-01&period=1").status_code == 400
    assert client.get("/api/forecasts/vintages?date=2026-01-15&period=49").status_code in (400, 422)
    assert client.get("/api/forecasts/vintages?date=2026-01-15&period=0").status_code in (400, 422)


def test_vintages_reports_explicit_limitation_when_none_cover_interval():
    store = loaded_store(actuals=[], forecasts=[])  # no WINDFOR rows at all
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get("/api/forecasts/vintages?date=2026-01-15&period=1").json()
    finally:
        app.dependency_overrides.clear()
    assert body["vintages"] == []
    assert body["limitation"] is not None and "unavailable" in body["limitation"]
    assert body["selected_publish_time"] is None
    assert body["error_mw"] is None


def test_vintages_never_marks_post_cutoff_vintage_as_eligible(synth_store):
    """Property: eligible_at_cutoff <=> publish <= cutoff, for every vintage."""
    from app.services.forecast_service import decision_cutoff_for

    store = synth_store
    cutoff = store.settings.decision_cutoff
    checked = 0
    for item_start in (datetime(2026, 1, 15, 0, tzinfo=timezone.utc),
                       datetime(2026, 1, 15, 12, tzinfo=timezone.utc)):
        from app.services.forecast_service import vintages_for_interval

        items, cutoff_utc, _ = vintages_for_interval(
            store.forecast_rows, store.selected, item_start, cutoff
        )
        for item in items:
            assert item.eligible_at_cutoff == (item.publish_time <= cutoff_utc)
            if not item.eligible_at_cutoff:
                assert item.selected is False  # never select a post-cutoff vintage
            checked += 1
    assert checked == 4
    # sanity: the helper's cutoff matches the endpoint convention
    assert decision_cutoff_for(datetime(2026, 1, 15, 12, tzinfo=timezone.utc), cutoff) == (
        datetime(2026, 1, 14, 9, 20, tzinfo=timezone.utc)
    )


# -- Feature D ---------------------------------------------------------------


def test_data_quality_reports_served_dataset_provenance(client):
    body = client.get("/api/data-quality").json()
    assert body["expected_halfhourly_intervals"] == 31 * 48
    assert body["matched_intervals"] == 31 * 48
    assert body["missing_actual_intervals"] == 0
    assert body["missing_forecast_intervals"] == 0
    assert body["coverage_pct"] == 100.0
    assert body["quality_status"] == "complete"
    assert body["actual_records_fetched"] == 31 * 48
    assert body["actual_records_present"] == 31 * 48
    assert body["forecast_records_fetched"] == 31 * 24 * 2  # 2 vintages/day
    assert body["eligible_forecast_records"] == 31 * 24  # only pre-cutoff rows
    assert body["selected_forecast_records"] == 31 * 24  # one winner per hour
    assert body["duplicate_records_dropped"] == {"actual": 0, "forecast": 0}
    assert body["decision_cutoff_utc"] == "09:20"
    assert body["dataset_source"] == "live fetch"  # synthetic rows loaded live
    assert len(body["limitations"]) >= 4
    assert any("indicative valuation" in item for item in body["limitations"])
    assert "not an external verification" in body["note"]


def test_data_quality_status_is_incomplete_when_intervals_missing():
    store = loaded_store(actuals=[], forecasts=[])  # every interval unmatched
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get("/api/data-quality").json()
    finally:
        app.dependency_overrides.clear()
    assert body["quality_status"] == "incomplete"
    assert body["matched_intervals"] == 0
    assert body["missing_actual_intervals"] == 31 * 48
    assert body["coverage_pct"] == 0.0
    # neutral label only - never "verified"
    assert "verif" not in body["quality_status"]


# -- Feature E ---------------------------------------------------------------


def test_insights_return_evidence_for_full_range(client):
    body = client.get("/api/insights?start=2026-01-01&end=2026-01-31&grain=halfhourly").json()
    assert body["grain"] == "halfhourly"
    assert 3 <= len(body["insights"]) <= 6
    ids = [i["id"] for i in body["insights"]]
    assert set(ids) >= {
        "bias_direction", "coverage", "worst_mae_day",
        "largest_abs_error", "error_concentration",
    }
    by_id = {i["id"]: i for i in body["insights"]}
    # synthetic forecast (9000+hour) is below synthetic actual (10000+sp) -> under-forecast
    bias = by_id["bias_direction"]
    assert bias["available"] is True
    assert "under-forecast" in bias["finding"]
    assert "matched intervals" in bias["evidence"]
    assert bias["period"] and bias["why_it_matters"]
    assert by_id["coverage"]["available"] is True
    assert "1488" in by_id["coverage"]["finding"]
    assert by_id["worst_mae_day"]["available"] is True
    assert by_id["largest_abs_error"]["available"] is True
    assert "over-forecast" in by_id["largest_abs_error"]["evidence"] or \
           "under-forecast" in by_id["largest_abs_error"]["evidence"] or \
           "signed error" in by_id["largest_abs_error"]["evidence"]
    assert "not a calibrated confidence bound" in by_id["error_concentration"]["evidence"]


def test_insights_mark_unavailable_instead_of_inventing_numbers():
    store = loaded_store(actuals=[], forecasts=[])  # no matched intervals
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            body = client.get("/api/insights?start=2026-01-01&end=2026-01-31").json()
    finally:
        app.dependency_overrides.clear()
    by_id = {i["id"]: i for i in body["insights"]}
    for insight_id in ("bias_direction", "worst_mae_day", "largest_abs_error"):
        item = by_id[insight_id]
        assert item["available"] is False
        assert item["unavailable_reason"]
        assert item["evidence"] == ""  # no fabricated numbers
    assert by_id["coverage"]["available"] is True  # coverage itself is known (0%)


def test_insights_reject_invalid_range(client):
    assert client.get("/api/insights?start=2026-02-01&end=2026-01-01").status_code == 400


# -- Feature F ---------------------------------------------------------------


def test_export_csv_matches_timeseries_rows(client):
    csv_resp = client.get("/api/export.csv?start=2026-01-15&end=2026-01-15&grain=hourly")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_resp.headers["content-disposition"]
    assert "2026-01-15" in csv_resp.headers["content-disposition"]

    ts_resp = client.get("/api/timeseries?start=2026-01-15&end=2026-01-15&grain=hourly")
    ts_rows = ts_resp.json()["rows"]

    reader = csv.reader(io.StringIO(csv_resp.text))
    header = next(reader)
    csv_rows = list(reader)
    assert header == [
        "delivery_timestamp_utc", "forecast_publish_time_utc", "forecast_mw",
        "actual_mw", "signed_error_mw", "absolute_error_mw", "status",
        "day_ahead_price_gbp_per_mwh", "error_value_gbp",
    ]
    assert len(csv_rows) == len(ts_rows) == 24

    # first delivery hour: forecast 9000, actual avg(sp1,sp2)=10001.5, error -1001.5
    first = csv_rows[0]
    assert first[0] == "2026-01-15T00:00:00Z"  # ISO 8601 Z, not +00:00
    assert first[1] == "2026-01-14T07:30:00Z"
    assert float(first[2]) == 9000.0
    assert float(first[3]) == 10001.5
    assert float(first[4]) == -1001.5
    assert float(first[5]) == 1001.5  # absolute error
    assert first[6] == "matched"
    assert first[4] == str(ts_rows[0]["error_mw"])  # identical value as timeseries
    # no prices in the synthetic fixture -> £ columns are empty, never 0
    assert first[7] == "" and first[8] == ""


def test_export_csv_missing_values_are_empty_not_zero():
    store = loaded_store(actuals=synth_period()[0], forecasts=[])  # actuals only
    app.dependency_overrides[get_store_dep] = lambda: store
    try:
        with TestClient(app) as client:
            resp = client.get("/api/export.csv?start=2026-01-15&end=2026-01-15&grain=hourly")
    finally:
        app.dependency_overrides.clear()
    reader = csv.reader(io.StringIO(resp.text))
    next(reader)  # skip header
    rows = list(reader)
    row = rows[0]
    assert row[2] == ""  # forecast missing -> empty, never "0"
    assert row[4] == ""  # error missing -> empty
    assert row[6] == "actual_only"  # actual present, forecast missing
    assert float(row[3]) == 10001.5  # actual still present


def test_export_csv_rejects_out_of_period(client):
    assert client.get("/api/export.csv?start=2026-03-01&end=2026-03-05").status_code == 400
