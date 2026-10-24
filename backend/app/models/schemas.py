"""Public API response schemas. The frontend only ever sees these shapes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field

Grain = Literal["hourly", "halfhourly"]


class CacheInfo(BaseModel):
    loaded: bool
    loaded_at: Optional[datetime] = None
    age_seconds: Optional[float] = None
    ttl_seconds: int
    refresh: str = "Lazy load on first data request; reloads when older than ttl_seconds"
    endpoint_refresh_param: str = "append ?refresh=true to any data endpoint to force reload"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "uk-wind-forecast-intelligence-api"
    period_start: date
    period_end: date
    decision_cutoff_utc: str = Field(
        description="Decision cutoff time-of-day applied to D-1, UTC (HH:MM)"
    )
    cache: CacheInfo


class AccuracyStats(BaseModel):
    grain: Grain
    n_expected: int = Field(description="Delivery intervals expected in the requested range")
    n_matched: int = Field(description="Intervals with both forecast and actual")
    n_missing: int = Field(description="n_expected - n_matched")
    coverage_pct: float = Field(description="100 * n_matched / n_expected")
    coverage_complete: bool
    mae_mw: Optional[float] = Field(None, description="Mean absolute error over matched intervals")
    rmse_mw: Optional[float] = Field(None, description="Root mean squared error over matched intervals")
    bias_mw: Optional[float] = Field(
        None, description="Mean signed error = forecast - actual over matched intervals"
    )
    mape_pct: Optional[float] = Field(
        None,
        description="Mean absolute percentage error; null when no valid denominator remains",
    )
    mape_excluded_intervals: int = Field(
        0, description="Matched intervals excluded from MAPE because actual == 0"
    )
    avg_forecast_mw: Optional[float]
    avg_actual_mw: Optional[float]
    status_counts: dict[str, int]


class OverviewResponse(BaseModel):
    period_start: date
    period_end: date
    decision_cutoff_utc: str
    selection_rule: str
    grain_note: str
    hourly: AccuracyStats
    halfhourly: AccuracyStats
    vintages_fetched: int
    selected_publish_times: list[datetime] = Field(
        description="Distinct publication times actually used, for audit"
    )


class TimeseriesRow(BaseModel):
    timestamp: datetime
    settlement_date: date
    settlement_period: Optional[int]
    actual_mw: Optional[float]
    forecast_mw: Optional[float]
    error_mw: Optional[float] = Field(None, description="forecast - actual; null if unmatched")
    status: Literal["matched", "forecast_only", "actual_only", "missing_both"]
    forecast_publish_time: Optional[datetime] = Field(
        None, description="Publication time of the selected decision-time vintage"
    )


class TimeseriesResponse(BaseModel):
    grain: Grain
    start: date
    end: date
    rows: list[TimeseriesRow]


class AccuracyResponse(AccuracyStats):
    start: date
    end: date
    note: str


class ForecastRowOut(BaseModel):
    timestamp: datetime
    forecast_mw: Optional[float]
    actual_mw: Optional[float]
    error_mw: Optional[float]
    status: str


class LatestForecastResponse(BaseModel):
    delivery_date: date
    decision_cutoff_utc: datetime
    selected_publish_time: Optional[datetime] = Field(
        None, description="Publication time of the latest vintage available at the cutoff"
    )
    selection_rule: str
    ignored_post_cutoff_publish_times: list[datetime] = Field(
        description="Vintages for this delivery date published after the cutoff (never used)"
    )
    hours: int
    rows: list[ForecastRowOut]


class ErrorDetail(BaseModel):
    detail: str
