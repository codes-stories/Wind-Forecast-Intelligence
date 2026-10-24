"""Point-in-time forecast selection, deduplication, alignment and caching.

Selection rule (verified for 31/31 days in Phase 1):
  For delivery interval T on day D, eligible vintages are those with
  publishTime <= (D-1 at the configured decision cutoff, UTC).  Among the
  eligible vintages covering T, the one with the maximum publishTime wins.
  Publication timestamps are never rewritten; post-cutoff vintages are
  never used for historical accuracy.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol, Sequence

from app.core.config import Settings
from app.models.records import (
    ActualRow,
    ForecastRow,
    IntervalPoint,
    classify,
)
from app.models.schemas import VintageItem
from app.services.elexon_client import ElexonClient

logger = logging.getLogger(__name__)

SELECTION_RULE = (
    "Latest WINDFOR vintage with publishTime <= decision cutoff (HH:MM UTC on D-1) "
    "that covers the delivery interval; post-cutoff vintages are excluded."
)
GRAIN_NOTE = (
    "WINDFOR is hourly while FUELHH is half-hourly. Metrics at hourly grain average the "
    "two half-hourly actuals; at halfhourly grain the hourly forecast value is mapped to "
    "both half-hours of its clock hour (documented mapping, no value substitution)."
)


class ElexonFetchClient(Protocol):
    def fetch_actuals(self, start: date, end: date) -> list[ActualRow]: ...

    def fetch_forecasts(self, publish_from: datetime, publish_to: datetime) -> list[ForecastRow]: ...


def decision_cutoff_for(interval_start: datetime, cutoff: time) -> datetime:
    """Decision moment for a delivery interval: cutoff time on the previous day."""
    day = interval_start.date() - timedelta(days=1)
    return datetime.combine(day, cutoff, tzinfo=timezone.utc)


def select_decision_time_forecasts(
    rows: Sequence[ForecastRow],
    cutoff: time,
    period_start: date,
    period_end: date,
) -> dict[datetime, ForecastRow]:
    """Latest eligible forecast per delivery hour (publishTime preserved)."""
    best: dict[datetime, ForecastRow] = {}
    for row in rows:
        day = row.start_time.date()
        if day < period_start or day > period_end:
            continue
        if row.publish_time > decision_cutoff_for(row.start_time, cutoff):
            continue  # published after the decision cutoff: never eligible
        current = best.get(row.start_time)
        if current is None or row.publish_time > current.publish_time:
            best[row.start_time] = row
    return best


def dedupe_actuals(rows: Sequence[ActualRow]) -> tuple[list[ActualRow], int]:
    """One row per settlement interval; on duplicates keep the latest publishTime."""
    best: dict[tuple[date, int], ActualRow] = {}
    dropped = 0
    for row in rows:
        key = (row.settlement_date, row.settlement_period)
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            dropped += 1
            if row.publish_time > existing.publish_time:
                best[key] = row
    return sorted(best.values(), key=lambda r: (r.settlement_date, r.settlement_period)), dropped


def dedupe_forecasts(rows: Sequence[ForecastRow]) -> tuple[list[ForecastRow], int]:
    """One row per (publishTime, startTime); identical duplicates dropped."""
    best: dict[tuple[datetime, datetime], ForecastRow] = {}
    dropped = 0
    for row in rows:
        key = (row.publish_time, row.start_time)
        if key in best:
            dropped += 1
            continue
        best[key] = row
    return sorted(best.values(), key=lambda r: (r.publish_time, r.start_time)), dropped


def build_hourly_points(
    period_start: date,
    period_end: date,
    actual_by_start: dict[datetime, ActualRow],
    selected: dict[datetime, ForecastRow],
) -> list[IntervalPoint]:
    points: list[IntervalPoint] = []
    day = period_start
    while day <= period_end:
        for hour in range(24):
            ts = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
            forecast = selected.get(ts)
            left = actual_by_start.get(ts)
            right = actual_by_start.get(ts + timedelta(minutes=30))
            actual = None
            if left is not None and right is not None:
                if left.generation_mw is not None and right.generation_mw is not None:
                    actual = (left.generation_mw + right.generation_mw) / 2  # MW average
            forecast_mw = forecast.generation_mw if forecast else None
            points.append(
                IntervalPoint(
                    timestamp=ts,
                    settlement_date=day,
                    settlement_period=None,
                    actual_mw=actual,
                    forecast_mw=forecast_mw,
                    status=classify(forecast_mw is not None, actual is not None),
                    forecast_publish_time=forecast.publish_time if forecast else None,
                )
            )
        day += timedelta(days=1)
    return points


def build_halfhourly_points(
    period_start: date,
    period_end: date,
    actual_by_start: dict[datetime, ActualRow],
    selected: dict[datetime, ForecastRow],
) -> list[IntervalPoint]:
    points: list[IntervalPoint] = []
    day = period_start
    while day <= period_end:
        for period in range(1, 49):
            offset = timedelta(minutes=30 * (period - 1))
            base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            ts = base + offset
            forecast = selected.get(ts.replace(minute=0))  # hourly value mapped to this half-hour
            actual_row = actual_by_start.get(ts)
            actual = actual_row.generation_mw if actual_row else None
            forecast_mw = forecast.generation_mw if forecast else None
            points.append(
                IntervalPoint(
                    timestamp=ts,
                    settlement_date=day,
                    settlement_period=period,
                    actual_mw=actual,
                    forecast_mw=forecast_mw,
                    status=classify(forecast_mw is not None, actual is not None),
                    forecast_publish_time=forecast.publish_time if forecast else None,
                )
            )
        day += timedelta(days=1)
    return points


def points_in_range(points: Sequence[IntervalPoint], start: date, end: date) -> list[IntervalPoint]:
    return [p for p in points if start <= p.settlement_date <= end]


# -- Feature A: historical vintage explorer ---------------------------------

VINTAGES_EMPTY_LIMITATION = (
    "No historical WINDFOR publications cover this delivery hour; forecast comparisons "
    "for this interval are unavailable (never backfilled or extrapolated)."
)


def vintages_for_interval(
    rows: Sequence[ForecastRow],
    selected: dict[datetime, ForecastRow],
    interval_start: datetime,
    cutoff: time,
) -> tuple[list[VintageItem], datetime, datetime | None]:
    """All publications covering an interval's clock hour, chronological.

    Returns (items, cutoff_utc, selected_publish_time).  Items carry
    `eligible_at_cutoff` (publish <= cutoff on D-1) and `selected` (the
    evaluation winner).  `change_mw` is the delta vs the previous
    publication; null for the earliest vintage.  Post-cutoff vintages are
    returned but flagged so the UI never mixes them into historical error.
    """
    clock_hour = interval_start.replace(minute=0, second=0, microsecond=0)
    cutoff_utc = decision_cutoff_for(interval_start, cutoff)
    winner = selected.get(clock_hour)
    covering = sorted(
        (r for r in rows if r.start_time == clock_hour),
        key=lambda r: r.publish_time,
    )
    items: list[VintageItem] = []
    previous: ForecastRow | None = None
    for row in covering:
        change = None
        if previous is not None and previous.generation_mw is not None and row.generation_mw is not None:
            change = round(row.generation_mw - previous.generation_mw, 3)
        items.append(
            VintageItem(
                publish_time=row.publish_time,
                forecast_mw=row.generation_mw,
                change_mw=change,
                eligible_at_cutoff=row.publish_time <= cutoff_utc,
                selected=winner is not None and row.publish_time == winner.publish_time,
            )
        )
        previous = row
    selected_publish = winner.publish_time if winner is not None else None
    return items, cutoff_utc, selected_publish


class DataStore:
    """Loads the study period once and serves aligned, auditable series."""

    def __init__(self, client: ElexonFetchClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.loaded_at: datetime | None = None
        self.stats: dict = {}
        self.hourly: list[IntervalPoint] = []
        self.halfhourly: list[IntervalPoint] = []
        self.selected: dict[datetime, ForecastRow] = {}
        self.forecast_rows: list[ForecastRow] = []
        self.actual_rows: list[ActualRow] = []

    @property
    def is_loaded(self) -> bool:
        return self.loaded_at is not None

    def age_seconds(self) -> float | None:
        if self.loaded_at is None:
            return None
        return (datetime.now(timezone.utc) - self.loaded_at).total_seconds()

    def load(self) -> None:
        s = self.settings
        actuals_raw = self.client.fetch_actuals(s.period_start, s.period_end)
        forecasts_raw = self.client.fetch_forecasts(s.forecast_publish_from, s.forecast_publish_to)
        logger.info(
            "fetched %s FUELHH rows and %s WINDFOR rows", len(actuals_raw), len(forecasts_raw)
        )

        actuals, actual_dupes = dedupe_actuals(actuals_raw)
        forecasts, forecast_dupes = dedupe_forecasts(forecasts_raw)
        selected = select_decision_time_forecasts(
            forecasts, s.decision_cutoff, s.period_start, s.period_end
        )

        actual_by_start = {row.start_time: row for row in actuals}
        self.actual_rows = actuals
        self.forecast_rows = forecasts
        self.selected = selected
        self.hourly = build_hourly_points(s.period_start, s.period_end, actual_by_start, selected)
        self.halfhourly = build_halfhourly_points(
            s.period_start, s.period_end, actual_by_start, selected
        )
        self.stats = {
            "actual_rows_fetched": len(actuals_raw),
            "forecast_rows_fetched": len(forecasts_raw),
            "actual_duplicates_dropped": actual_dupes,
            "forecast_duplicates_dropped": forecast_dupes,
            "actual_null_values": sum(1 for r in actuals if r.generation_mw is None),
            "forecast_null_values": sum(1 for r in forecasts if r.generation_mw is None),
            "vintages_fetched": len({r.publish_time for r in forecasts}),
            "selected_publish_times": sorted({r.publish_time for r in selected.values()}),
            "eligible_forecast_rows": sum(
                1
                for r in forecasts
                if s.period_start <= r.start_time.date() <= s.period_end
                and r.publish_time <= decision_cutoff_for(r.start_time, s.decision_cutoff)
            ),
        }
        self.loaded_at = datetime.now(timezone.utc)


# -- process-wide cache ------------------------------------------------------
_store: DataStore | None = None
_lock = threading.Lock()


def build_store(settings: Settings) -> DataStore:
    return DataStore(ElexonClient(settings), settings)


def get_store(settings: Settings, refresh: bool = False) -> DataStore:
    """Return the cached store, loading it when absent, stale, or refresh=True.

    Cache policy: in-process, single row-set for the whole study period,
    TTL = settings.cache_ttl_seconds, forced reload via ?refresh=true.
    No database: the dataset is ~1488 actual + ~18.7k forecast rows.
    """
    global _store
    with _lock:
        stale = _store is None or not _store.is_loaded
        if not stale and _store is not None:
            age = _store.age_seconds() or 0
            stale = age > settings.cache_ttl_seconds
        if refresh or stale:
            store = build_store(settings)
            store.load()  # ElexonError propagates -> 502 handler
            _store = store
        return _store


def cache_status(settings: Settings) -> dict:
    with _lock:
        if _store is None or not _store.is_loaded:
            return {"loaded": False, "ttl_seconds": settings.cache_ttl_seconds}
        return {
            "loaded": True,
            "loaded_at": _store.loaded_at,
            "age_seconds": round(_store.age_seconds() or 0, 1),
            "ttl_seconds": settings.cache_ttl_seconds,
        }


def reset_cache() -> None:
    """Test hook."""
    global _store
    with _lock:
        _store = None
