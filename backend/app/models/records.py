"""Internal record types (normalised Elexon data, API-independent)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

STATUS_MATCHED = "matched"
STATUS_FORECAST_ONLY = "forecast_only"
STATUS_ACTUAL_ONLY = "actual_only"
STATUS_MISSING_BOTH = "missing_both"


@dataclass(frozen=True)
class ActualRow:
    """One FUELHH half-hourly outturn interval (fuelType=WIND)."""

    settlement_date: date
    settlement_period: int  # 1..48
    start_time: datetime  # delivery interval start, UTC
    publish_time: datetime  # publication time, UTC (interval end + publication lag)
    generation_mw: float | None


@dataclass(frozen=True)
class ForecastRow:
    """One WINDFOR hourly forecast value from a single vintage."""

    publish_time: datetime  # vintage publication time, UTC (never rewritten)
    start_time: datetime  # delivery hour start, UTC
    generation_mw: float | None


@dataclass(frozen=True)
class IntervalPoint:
    """Joined forecast/actual for one delivery interval at the active grain."""

    timestamp: datetime
    settlement_date: date
    settlement_period: int | None  # None at hourly grain
    actual_mw: float | None
    forecast_mw: float | None
    status: str
    forecast_publish_time: datetime | None

    @property
    def error_mw(self) -> float | None:
        if self.actual_mw is None or self.forecast_mw is None:
            return None
        return self.forecast_mw - self.actual_mw


def classify(forecast_present: bool, actual_present: bool) -> str:
    if forecast_present and actual_present:
        return STATUS_MATCHED
    if forecast_present:
        return STATUS_FORECAST_ONLY
    if actual_present:
        return STATUS_ACTUAL_ONLY
    return STATUS_MISSING_BOTH
