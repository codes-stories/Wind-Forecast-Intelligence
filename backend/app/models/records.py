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
class PriceRow:
    """One market-index price point for a settlement interval.

    price_gbp_per_mwh is the day-ahead mid price in £/MWh (Elexon
    market-index, APXMIDP provider); used only for the indicative
    valuation of forecast error, never for settlement figures.
    """

    settlement_date: date
    settlement_period: int  # 1..48
    start_time: datetime  # delivery interval start, UTC
    price_gbp_per_mwh: float


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
    # day-ahead mid price for this interval; null when price data is absent
    # (hourly grain: mean of the clock hour's two half-hour prices)
    price_gbp_per_mwh: float | None = None

    @property
    def error_mw(self) -> float | None:
        if self.actual_mw is None or self.forecast_mw is None:
            return None
        return self.forecast_mw - self.actual_mw

    @property
    def duration_hours(self) -> float:
        """Interval length: 0.5h at halfhourly grain, 1h at hourly grain."""
        return 0.5 if self.settlement_period is not None else 1.0

    @property
    def error_value_gbp(self) -> float | None:
        """Indicative value of the error at the interval price: MW x £/MWh x hours.

        Null when unmatched or when no price is available for the interval.
        """
        error = self.error_mw
        if error is None or self.price_gbp_per_mwh is None:
            return None
        return error * self.price_gbp_per_mwh * self.duration_hours


def classify(forecast_present: bool, actual_present: bool) -> str:
    if forecast_present and actual_present:
        return STATUS_MATCHED
    if forecast_present:
        return STATUS_FORECAST_ONLY
    if actual_present:
        return STATUS_ACTUAL_ONLY
    return STATUS_MISSING_BOTH
