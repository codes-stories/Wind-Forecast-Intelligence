"""HTTP routes. Response shapes are defined in app.models.schemas only."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import Settings, get_settings
from app.models.schemas import (
    AccuracyResponse,
    CacheInfo,
    ForecastRowOut,
    HealthResponse,
    LatestForecastResponse,
    OverviewResponse,
    TimeseriesResponse,
    TimeseriesRow,
)
from app.services import forecast_service, metrics_service
from app.services.forecast_service import (
    GRAIN_NOTE,
    SELECTION_RULE,
    DataStore,
)

router = APIRouter()

GrainParam = Literal["hourly", "halfhourly"]


def get_store_dep(
    refresh: bool = Query(
        False, description="Force a reload of the cached January 2026 dataset"
    ),
) -> DataStore:
    return forecast_service.get_store(get_settings(), refresh=refresh)


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


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness + explicit cache state. Never calls the upstream API."""
    return HealthResponse(
        status="ok",
        period_start=settings.period_start,
        period_end=settings.period_end,
        decision_cutoff_utc=settings.decision_cutoff_label,
        cache=CacheInfo(**forecast_service.cache_status(settings)),
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
    points, _ = _points(store, grain)
    rows = [
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
