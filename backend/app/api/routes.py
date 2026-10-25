"""HTTP routes. Response shapes are defined in app.models.schemas only."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings, normalize_fuel_type
from app.models.schemas import (
    AccuracyResponse,
    CacheInfo,
    DataQualityResponse,
    ForecastRowOut,
    HealthResponse,
    InsightsResponse,
    LatestForecastResponse,
    OverviewResponse,
    TimeseriesResponse,
    TimeseriesRow,
    VintageIntervalResponse,
)
from app.services import forecast_service, insights_service, metrics_service
from app.services.forecast_service import (
    GRAIN_NOTE,
    SELECTION_RULE,
    VINTAGES_EMPTY_LIMITATION,
    DataStore,
)

router = APIRouter()

GrainParam = Literal["hourly", "halfhourly"]

DATA_QUALITY_LIMITATIONS = [
    "WINDFOR generation is assumed to be in MW; the unit is not documented by Elexon.",
    "WINDFOR vintages cover roughly (P-1) 21:00 to (P+2) 21:00 UTC, so hours near the "
    "period edges are covered by fewer publications.",
    "Half-hourly evaluation maps the hourly WINDFOR value to both half-hours of its "
    "clock hour (documented mapping, no value substitution).",
    "MAPE excludes intervals where the actual is zero; the exclusion count is reported.",
    "The dataset is cached in memory for the configured TTL; cache age is reported here.",
]


def _fuel_type(fuel_type: Optional[str], settings: Settings) -> str:
    """Resolve ?fuel_type= against the configured default, rejecting unknown fuels."""
    try:
        return normalize_fuel_type(fuel_type or settings.fuel_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_store_dep(
    refresh: bool = Query(
        False, description="Force a reload of the cached January 2026 dataset"
    ),
    fuel_type: Optional[str] = Query(
        None,
        description=(
            "FUELHH fuel filter (e.g. WIND, NUCLEAR, CCGT); defaults to the "
            "configured FUEL_TYPE. Only WIND has a WINDFOR forecast to compare."
        ),
    ),
) -> DataStore:
    settings = get_settings()
    return forecast_service.get_store(
        settings, refresh=refresh, fuel_type=_fuel_type(fuel_type, settings)
    )


def _validate_range(start: Optional[date], end: Optional[date], settings: Settings) -> tuple[date, date]:
    start = start or settings.period_start
    end = end or settings.period_end
    if start > end:
        raise HTTPException(status_code=400, detail="start must be on or before end")
    if start < settings.period_start or end > settings.period_end:
        raise HTTPException(
            status_code=400,
            detail=(
                f"range must be within the reporting period "
                f"{settings.period_start.isoformat()}..{settings.period_end.isoformat()}"
            ),
        )
    return start, end


def _points(store: DataStore, grain: GrainParam):
    return (store.hourly if grain == "hourly" else store.halfhourly,
            24 if grain == "hourly" else 48)


def _expected_count(start: date, end: date, grain: GrainParam) -> int:
    days = (end - start).days + 1
    return days * (24 if grain == "hourly" else 48)


def _timeseries_rows(store: DataStore, start: date, end: date, grain: GrainParam) -> list[TimeseriesRow]:
    """Single row builder shared by /api/timeseries and /api/export.csv."""
    points, _ = _points(store, grain)
    return [
        TimeseriesRow(
            timestamp=p.timestamp,
            settlement_date=p.settlement_date,
            settlement_period=p.settlement_period,
            actual_mw=p.actual_mw,
            forecast_mw=p.forecast_mw,
            error_mw=p.error_mw,
            status=p.status,  # type: ignore[arg-type]
            forecast_publish_time=p.forecast_publish_time,
        )
        for p in forecast_service.points_in_range(points, start, end)
    ]


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health(
    fuel_type: Optional[str] = Query(None, description="Fuel filter to report cache state for"),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Liveness + explicit cache state. Never calls the upstream API."""
    fuel = _fuel_type(fuel_type, settings)
    return HealthResponse(
        status="ok",
        period_start=settings.period_start,
        period_end=settings.period_end,
        decision_cutoff_utc=settings.decision_cutoff_label,
        fuel_type=fuel,
        cache=CacheInfo(**forecast_service.cache_status(settings, fuel)),
    )


@router.get("/api/overview", response_model=OverviewResponse, tags=["analysis"])
def overview(
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> OverviewResponse:
    """Headline accuracy for the whole period at both grains, with coverage."""
    return OverviewResponse(
        period_start=settings.period_start,
        period_end=settings.period_end,
        decision_cutoff_utc=settings.decision_cutoff_label,
        selection_rule=SELECTION_RULE,
        grain_note=GRAIN_NOTE,
        hourly=metrics_service.compute_stats(store.hourly, len(store.hourly), "hourly"),
        halfhourly=metrics_service.compute_stats(
            store.halfhourly, len(store.halfhourly), "halfhourly"
        ),
        vintages_fetched=store.stats.get("vintages_fetched", 0),
        selected_publish_times=store.stats.get("selected_publish_times", []),
    )


@router.get("/api/timeseries", response_model=TimeseriesResponse, tags=["analysis"])
def timeseries(
    start: Optional[date] = Query(None, description="First delivery date (inclusive)"),
    end: Optional[date] = Query(None, description="Last delivery date (inclusive)"),
    grain: GrainParam = Query(
        "halfhourly",
        description="halfhourly (48/day, forecast mapped from its clock hour) or hourly (24/day)",
    ),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> TimeseriesResponse:
    start, end = _validate_range(start, end, settings)
    rows = _timeseries_rows(store, start, end, grain)
    return TimeseriesResponse(grain=grain, start=start, end=end, rows=rows)


@router.get("/api/accuracy", response_model=AccuracyResponse, tags=["analysis"])
def accuracy(
    start: Optional[date] = Query(None, description="First delivery date (inclusive)"),
    end: Optional[date] = Query(None, description="Last delivery date (inclusive)"),
    grain: GrainParam = Query("hourly", description="Grain for the metric computation"),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> AccuracyResponse:
    start, end = _validate_range(start, end, settings)
    points, _ = _points(store, grain)
    subset = forecast_service.points_in_range(points, start, end)
    stats = metrics_service.compute_stats(subset, _expected_count(start, end, grain), grain)
    note = (
        "Metrics computed over matched intervals only; see coverage_pct and n_missing. "
        "MAPE excludes matched intervals where actual == 0 (mape_excluded_intervals)."
    )
    return AccuracyResponse(**stats.model_dump(), start=start, end=end, note=note)


@router.get("/api/forecasts/latest", response_model=LatestForecastResponse, tags=["forecasts"])
def latest_forecast(
    delivery_date: Optional[date] = Query(
        None, description="Delivery day to inspect (default: last day of the period)"
    ),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> LatestForecastResponse:
    """Latest forecast ELIGIBLE at the historical decision cutoff for a delivery day.

    'latest' means newest vintage published at or before the cutoff - never a
    post-cutoff publication.
    """
    delivery_date = delivery_date or settings.period_end
    if not (settings.period_start <= delivery_date <= settings.period_end):
        raise HTTPException(
            status_code=400,
            detail=(
                f"delivery_date must be within "
                f"{settings.period_start.isoformat()}..{settings.period_end.isoformat()}"
            ),
        )
    cutoff = datetime.combine(
        delivery_date - timedelta(days=1),
        settings.decision_cutoff,
        tzinfo=timezone.utc,
    )
    publish_times = sorted(
        {r.publish_time for r in store.forecast_rows if r.start_time.date() == delivery_date}
    )
    selected_times = sorted(
        {r.publish_time for r in store.selected.values() if r.start_time.date() == delivery_date}
    )
    selected_publish = max(selected_times) if selected_times else None
    ignored = [t for t in publish_times if t > cutoff]

    rows: list[ForecastRowOut] = []
    for p in store.hourly:
        if p.settlement_date == delivery_date:
            rows.append(
                ForecastRowOut(
                    timestamp=p.timestamp,
                    forecast_mw=p.forecast_mw,
                    actual_mw=p.actual_mw,
                    error_mw=p.error_mw,
                    status=p.status,
                )
            )
    if not rows:
        raise HTTPException(status_code=404, detail="no forecast rows for that delivery date")
    return LatestForecastResponse(
        delivery_date=delivery_date,
        decision_cutoff_utc=cutoff,
        selected_publish_time=selected_publish,
        selection_rule=SELECTION_RULE,
        ignored_post_cutoff_publish_times=ignored,
        hours=len(rows),
        rows=rows,
    )


# -- Feature A: historical forecast vintage explorer ------------------------


@router.get("/api/forecasts/vintages", response_model=VintageIntervalResponse, tags=["forecasts"])
def interval_vintages(
    date_: Optional[date] = Query(None, alias="date", description="Delivery date (UTC)"),
    period: int = Query(..., ge=1, le=48, description="Half-hour settlement period 1..48"),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> VintageIntervalResponse:
    """Every WINDFOR publication covering one delivery half-hour, chronological.

    Eligible-at-cutoff and selected vintages are flagged; post-cutoff
    publications are returned for context but marked ineligible so they are
    never mixed into historical error.
    """
    day = date_ or settings.period_end
    if not (settings.period_start <= day <= settings.period_end):
        raise HTTPException(
            status_code=400,
            detail=(
                f"date must be within "
                f"{settings.period_start.isoformat()}..{settings.period_end.isoformat()}"
            ),
        )
    interval_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(
        minutes=30 * (period - 1)
    )
    clock_hour = interval_start.replace(minute=0, second=0, microsecond=0)
    items, cutoff_utc, selected_publish = forecast_service.vintages_for_interval(
        store.forecast_rows, store.selected, interval_start, settings.decision_cutoff
    )
    winner = store.selected.get(clock_hour)
    actual_row = next(
        (p for p in store.halfhourly if p.timestamp == interval_start), None
    )
    actual_mw = actual_row.actual_mw if actual_row else None
    selected_mw = winner.generation_mw if winner else None
    error = (
        selected_mw - actual_mw
        if selected_mw is not None and actual_mw is not None
        else None
    )
    eligible = [i for i in items if i.eligible_at_cutoff]
    post = [i for i in items if not i.eligible_at_cutoff]
    latest = items[-1] if items else None
    return VintageIntervalResponse(
        delivery_timestamp=interval_start,
        settlement_date=day,
        settlement_period=period,
        clock_hour=clock_hour,
        cutoff_utc=cutoff_utc,
        actual_mw=actual_mw,
        selected_publish_time=selected_publish,
        selected_forecast_mw=selected_mw,
        error_mw=round(error, 3) if error is not None else None,
        absolute_error_mw=round(abs(error), 3) if error is not None else None,
        latest_publish_time=latest.publish_time if latest else None,
        latest_forecast_mw=latest.forecast_mw if latest else None,
        eligible_count=len(eligible),
        post_cutoff_count=len(post),
        vintages=items,
        limitation=None if items else VINTAGES_EMPTY_LIMITATION,
        note=(
            "All publications covering this clock hour, chronological. eligible_at_cutoff "
            "means publishTime <= decision cutoff on D-1; selected is the vintage used "
            "for historical accuracy. latest_* may be a post-cutoff publication and is "
            "never used for evaluation."
        ),
    )


# -- Feature D: data quality and provenance ---------------------------------


@router.get("/api/data-quality", response_model=DataQualityResponse, tags=["ops"])
def data_quality(
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> DataQualityResponse:
    """Served-dataset provenance: retrieved vs matched counts, cache state, limitations."""
    half = store.halfhourly
    matched = sum(1 for p in half if p.status == "matched")
    missing_actual = sum(1 for p in half if p.status in ("forecast_only", "missing_both"))
    missing_forecast = sum(1 for p in half if p.status in ("actual_only", "missing_both"))
    expected = len(half)
    coverage = (100.0 * matched / expected) if expected else 0.0
    cache = forecast_service.cache_status(settings, store.fuel_type)
    limitations = list(DATA_QUALITY_LIMITATIONS)
    if not store.forecast_available:
        limitations.append(
            "WINDFOR publishes wind only, so this fuel has actuals but no forecast "
            "to compare; every interval is reported as actual_only."
        )
    return DataQualityResponse(
        sources={
            "actual": f"Elexon FUELHH ({store.fuel_type.lower()}, half-hourly)",
            "forecast": (
                "Elexon WINDFOR (hourly vintage)"
                if store.forecast_available
                else "unavailable for this fuel (WINDFOR is wind-only)"
            ),
        },
        fuel_type=store.fuel_type,
        forecast_available=store.forecast_available,
        period_start=settings.period_start,
        period_end=settings.period_end,
        decision_cutoff_utc=settings.decision_cutoff_label,
        expected_halfhourly_intervals=expected,
        actual_records_fetched=int(store.stats.get("actual_rows_fetched", 0)),
        actual_records_present=max(
            0,
            len(store.actual_rows) - int(store.stats.get("actual_null_values", 0)),
        ),
        forecast_records_fetched=int(store.stats.get("forecast_rows_fetched", 0)),
        eligible_forecast_records=int(store.stats.get("eligible_forecast_rows", 0)),
        selected_forecast_records=len(store.selected),
        matched_intervals=matched,
        missing_actual_intervals=missing_actual,
        missing_forecast_intervals=missing_forecast,
        coverage_pct=round(coverage, 2),
        duplicate_records_dropped={
            "actual": int(store.stats.get("actual_duplicates_dropped", 0)),
            "forecast": int(store.stats.get("forecast_duplicates_dropped", 0)),
        },
        null_values_in_source={
            "actual": int(store.stats.get("actual_null_values", 0)),
            "forecast": int(store.stats.get("forecast_null_values", 0)),
        },
        cache_loaded_at=cache.get("loaded_at"),
        cache_age_seconds=cache.get("age_seconds"),
        cache_ttl_seconds=int(cache.get("ttl_seconds", settings.cache_ttl_seconds)),
        quality_status="complete" if matched == expected and expected > 0 else "incomplete",
        limitations=limitations,
        note=(
            "Counts are computed from the dataset currently served by this API. "
            "'complete' means every expected interval is matched; it is not an "
            "external verification of the upstream feed."
        ),
    )


# -- Feature E: evidence-based insights -------------------------------------


@router.get("/api/insights", response_model=InsightsResponse, tags=["analysis"])
def insights(
    start: Optional[date] = Query(None, description="First delivery date (inclusive)"),
    end: Optional[date] = Query(None, description="Last delivery date (inclusive)"),
    grain: GrainParam = Query("halfhourly", description="Grain used to derive the insights"),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> InsightsResponse:
    """Deterministic findings computed from the served range (no LLM, no rules engine)."""
    start, end = _validate_range(start, end, settings)
    points, _ = _points(store, grain)
    subset = forecast_service.points_in_range(points, start, end)
    items = insights_service.build_insights(
        subset, start, end, grain, _expected_count(start, end, grain)  # type: ignore[arg-type]
    )
    return InsightsResponse(
        grain=grain,  # type: ignore[arg-type]
        start=start,
        end=end,
        insights=items,
        note=(
            "Every insight lists the numbers behind it (evidence) for the selected "
            "range. Insights are historical observations over matched intervals, "
            "not forecasts or causal explanations."
        ),
    )


# -- Feature F: analyst CSV export -------------------------------------------


_CSV_HEADER = [
    "delivery_timestamp_utc",
    "forecast_publish_time_utc",
    "forecast_mw",
    "actual_mw",
    "signed_error_mw",
    "absolute_error_mw",
    "status",
]


def _iso_z(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _csv_num(value: Optional[float]) -> str:
    return "" if value is None else repr(float(value))


@router.get("/api/export.csv", tags=["export"])
def export_csv(
    start: Optional[date] = Query(None, description="First delivery date (inclusive)"),
    end: Optional[date] = Query(None, description="Last delivery date (inclusive)"),
    grain: GrainParam = Query("halfhourly", description="Grain of the exported rows"),
    store: DataStore = Depends(get_store_dep),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Same rows as /api/timeseries as CSV; missing values are empty (never 0)."""
    start, end = _validate_range(start, end, settings)
    rows = _timeseries_rows(store, start, end, grain)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)
    for row in rows:
        abs_err = (
            abs(row.error_mw)
            if row.error_mw is not None and row.actual_mw is not None and row.forecast_mw is not None
            else None
        )
        writer.writerow(
            [
                _iso_z(row.timestamp),
                _iso_z(row.forecast_publish_time),
                _csv_num(row.forecast_mw),
                _csv_num(row.actual_mw),
                _csv_num(row.error_mw),
                _csv_num(abs_err),
                row.status,
            ]
        )
    filename = f"wind_forecast_{start.isoformat()}_{end.isoformat()}_{grain}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
