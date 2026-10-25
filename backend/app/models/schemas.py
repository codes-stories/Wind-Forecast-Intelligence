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
    source: str = Field(
        default="not loaded",
        description="Where the served dataset came from: 'live fetch' or a shipped snapshot",
    )
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
    fuel_type: str = Field(description="FUELHH fuel filter in effect (default WIND)")
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
    median_abs_error_mw: Optional[float] = Field(
        None, description="Median |error| over matched intervals (historical statistic)"
    )
    p90_abs_error_mw: Optional[float] = Field(
        None,
        description=(
            "90th percentile (nearest-rank) of |error| over matched intervals; "
            "historical error statistic, not a calibrated confidence bound; "
            "null when fewer than 10 matched intervals"
        ),
    )
    n_missing_actual: int = Field(
        0, description="Intervals where the actual is missing (forecast_only + missing_both)"
    )
    n_missing_forecast: int = Field(
        0, description="Intervals where the forecast is missing (actual_only + missing_both)"
    )
    avg_forecast_mw: Optional[float]
    avg_actual_mw: Optional[float]
    status_counts: dict[str, int]
    # -- indicative £ valuation of the error (day-ahead market-index price) --
    n_priced_intervals: int = Field(
        0, description="Matched intervals with a day-ahead price (subset of n_matched)"
    )
    price_coverage_pct: float = Field(
        0.0, description="100 * n_priced_intervals / n_matched; 0 when nothing is priced"
    )
    net_error_value_gbp: Optional[float] = Field(
        None,
        description=(
            "Signed value of the forecast error: sum(error x price x hours) over "
            "priced matched intervals; positive = over-forecast would have cost more. "
            "Indicative only, null when no priced interval exists."
        ),
    )
    abs_error_value_gbp: Optional[float] = Field(
        None,
        description=(
            "Absolute value of the error: sum(|error| x price x hours) over priced "
            "matched intervals; the 'cost of being wrong' headline. Indicative only, "
            "null when no priced interval exists."
        ),
    )
    price_source: Optional[str] = Field(
        None, description="Price feed behind the £ figures; null when unpriced"
    )


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
    price_gbp_per_mwh: Optional[float] = Field(
        None,
        description=(
            "Day-ahead mid price (APXMIDP) for this interval; null when price "
            "data is unavailable (hourly grain: mean of the clock hour's prices)"
        ),
    )
    error_value_gbp: Optional[float] = Field(
        None,
        description=(
            "Indicative value of error_mw at price x interval hours; null when "
            "unmatched or unpriced. Not an imbalance settlement figure."
        ),
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


# -- Feature A: historical forecast vintage explorer -------------------------


class VintageItem(BaseModel):
    publish_time: datetime = Field(description="Publication timestamp of this vintage (UTC, never rewritten)")
    forecast_mw: Optional[float] = Field(None, description="Forecast generation for the delivery hour (MW)")
    change_mw: Optional[float] = Field(
        None, description="Change vs the previous publication; null for the earliest vintage"
    )
    eligible_at_cutoff: bool = Field(
        description="publishTime <= decision cutoff on D-1 (eligible for historical evaluation)"
    )
    selected: bool = Field(description="The vintage actually used for this interval's accuracy evaluation")


class VintageIntervalResponse(BaseModel):
    delivery_timestamp: datetime
    settlement_date: date
    settlement_period: int
    clock_hour: datetime = Field(description="Hourly forecast key this interval maps to (UTC)")
    cutoff_utc: datetime = Field(description="Decision cutoff moment for this delivery day (D-1 HH:MM UTC)")
    actual_mw: Optional[float]
    selected_publish_time: Optional[datetime]
    selected_forecast_mw: Optional[float]
    error_mw: Optional[float] = Field(None, description="selected forecast - actual; null if unmatched")
    absolute_error_mw: Optional[float]
    latest_publish_time: Optional[datetime] = Field(
        None, description="Most recent publication covering this hour (may be after the cutoff)"
    )
    latest_forecast_mw: Optional[float]
    eligible_count: int
    post_cutoff_count: int
    vintages: list[VintageItem]
    limitation: Optional[str] = Field(
        None, description="Set when no historical publications cover the interval; comparisons are disabled"
    )
    note: str


# -- Feature D: data quality and provenance ---------------------------------


class DataQualityResponse(BaseModel):
    sources: dict[str, str]
    fuel_type: str = Field(description="FUELHH fuel filter the served dataset was built from")
    forecast_available: bool = Field(
        description="False for non-wind fuels: WINDFOR publishes wind only"
    )
    period_start: date
    period_end: date
    decision_cutoff_utc: str
    expected_halfhourly_intervals: int
    actual_records_fetched: int
    actual_records_present: int
    forecast_records_fetched: int
    eligible_forecast_records: int = Field(
        description="Deduplicated WINDFOR rows published at or before the cutoff for in-period hours"
    )
    selected_forecast_records: int = Field(description="Distinct hourly winners used (one per delivery hour)")
    matched_intervals: int
    missing_actual_intervals: int
    missing_forecast_intervals: int
    coverage_pct: float
    duplicate_records_dropped: dict[str, int]
    null_values_in_source: dict[str, int]
    cache_loaded_at: Optional[datetime]
    cache_age_seconds: Optional[float]
    cache_ttl_seconds: int
    dataset_source: str = Field(
        default="live fetch",
        description="Whether the served rows came from a live fetch or a shipped snapshot",
    )
    quality_status: str = Field(
        description="'complete' when every expected interval is matched, else 'incomplete'"
    )
    limitations: list[str]
    note: str


# -- Feature G: decision lab (cutoff sensitivity, calibration, skill) --------


class CutoffCandidate(BaseModel):
    cutoff_utc: str = Field(description="Candidate decision cutoff time-of-day on D-1 (HH:MM UTC)")
    is_current: bool = Field(description="True for the configured decision cutoff in use")
    mae_mw: Optional[float]
    rmse_mw: Optional[float]
    bias_mw: Optional[float]
    n_matched: int
    coverage_pct: float
    delta_mae_mw: Optional[float] = Field(
        None,
        description="candidate MAE - current MAE; negative = lower error than the current cutoff",
    )


class CutoffSensitivityResponse(BaseModel):
    start: date
    end: date
    current_cutoff_utc: str
    candidates: list[CutoffCandidate]
    best_cutoff_utc: Optional[str] = Field(
        None, description="Candidate with the lowest MAE (null when no candidate has a sample)"
    )
    best_delta_mae_mw: Optional[float] = Field(
        None, description="best candidate MAE - current MAE (<= 0 means an improvement)"
    )
    rule: str = Field(description="Selection rule applied with each candidate cutoff")
    note: str
    limitation: Optional[str] = None


class CalibrationStats(BaseModel):
    hours_total: int = Field(description="Delivery hours in the requested range")
    hours_evaluated: int = Field(
        description="Hours with an actual and at least one pre-cutoff vintage"
    )
    hours_inside: int = Field(description="Actual within the pre-cutoff vintage envelope")
    hours_below: int = Field(description="Actual below the envelope (forecast too high)")
    hours_above: int = Field(description="Actual above the envelope (forecast too low)")
    inside_pct: Optional[float] = Field(None, description="100 * hours_inside / hours_evaluated")
    avg_envelope_width_mw: Optional[float] = Field(
        None, description="Mean max-min spread of pre-cutoff vintages (zero with one vintage)"
    )
    avg_vintages_per_hour: Optional[float] = Field(
        None, description="Mean number of pre-cutoff vintages behind each envelope"
    )
    limitation: str


class SkillStats(BaseModel):
    grain: Grain = "halfhourly"
    n_matched: int = Field(description="WINDFOR matched intervals in the range")
    n_evaluated: int = Field(
        description="Common sample: matched intervals where persistence (actual 24h earlier) exists"
    )
    n_persistence_unavailable: int = Field(
        description="Matched intervals excluded because the prior day's actual is outside the dataset"
    )
    windfor_mae_mw: Optional[float] = Field(None, description="MAE on the common sample")
    persistence_mae_mw: Optional[float] = Field(
        None, description="MAE of the persistence baseline on the common sample"
    )
    skill_pct: Optional[float] = Field(
        None,
        description="100 * (1 - windfor_mae / persistence_mae); positive = forecast beats persistence",
    )
    note: str


class BenchmarksResponse(BaseModel):
    start: date
    end: date
    current_cutoff_utc: str
    calibration: CalibrationStats
    skill: SkillStats
    note: str


# -- Feature E: evidence-based insights -------------------------------------


class InsightItem(BaseModel):
    id: str
    finding: str
    evidence: str
    period: str
    why_it_matters: str
    available: bool = True
    unavailable_reason: Optional[str] = None


class InsightsResponse(BaseModel):
    grain: Grain
    start: date
    end: date
    insights: list[InsightItem]
    note: str
