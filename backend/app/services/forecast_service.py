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

from app.core.config import Settings, normalize_fuel_type
from app.models.records import (
    ActualRow,
    ForecastRow,
    IntervalPoint,
    PriceRow,
    classify,
)
from app.models.schemas import VintageItem
from app.services import snapshot_service
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
    def fetch_actuals(
        self, start: date, end: date, fuel_type: str | None = None
    ) -> list[ActualRow]: ...

    def fetch_forecasts(self, publish_from: datetime, publish_to: datetime) -> list[ForecastRow]: ...

    def fetch_prices(self, start: date, end: date) -> list[PriceRow]: ...


# WINDFOR publishes wind only: any other FUELHH fuel has actuals but no forecast.
FORECAST_FUEL = "WIND"

# (settlementDate, settlementPeriod) -> day-ahead mid price in £/MWh
PriceMap = dict[tuple[date, int], float]


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


def _hourly_price(day: date, hour: int, prices: PriceMap) -> float | None:
    """Price for an hourly point: mean of the clock hour's available half-hour prices."""
    p1 = prices.get((day, hour * 2 + 1))
    p2 = prices.get((day, hour * 2 + 2))
    values = [v for v in (p1, p2) if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_hourly_points(
    period_start: date,
    period_end: date,
    actual_by_start: dict[datetime, ActualRow],
    selected: dict[datetime, ForecastRow],
    prices: PriceMap | None = None,
) -> list[IntervalPoint]:
    prices = prices or {}
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
                    price_gbp_per_mwh=_hourly_price(day, hour, prices),
                )
            )
        day += timedelta(days=1)
    return points


def build_halfhourly_points(
    period_start: date,
    period_end: date,
    actual_by_start: dict[datetime, ActualRow],
    selected: dict[datetime, ForecastRow],
    prices: PriceMap | None = None,
) -> list[IntervalPoint]:
    prices = prices or {}
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
                    price_gbp_per_mwh=prices.get((day, period)),
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

    def __init__(
        self, client: ElexonFetchClient, settings: Settings, fuel_type: str | None = None
    ):
        self.client = client
        self.settings = settings
        self.fuel_type = normalize_fuel_type(fuel_type or settings.fuel_type)
        self.loaded_at: datetime | None = None
        self.stats: dict = {}
        self.hourly: list[IntervalPoint] = []
        self.halfhourly: list[IntervalPoint] = []
        self.selected: dict[datetime, ForecastRow] = {}
        self.forecast_rows: list[ForecastRow] = []
        self.actual_rows: list[ActualRow] = []
        self.prices: PriceMap = {}

    @property
    def forecast_available(self) -> bool:
        """WINDFOR carries wind only, so other fuels have actuals but no forecast."""
        return self.fuel_type == FORECAST_FUEL

    @property
    def is_loaded(self) -> bool:
        return self.loaded_at is not None

    def age_seconds(self) -> float | None:
        if self.loaded_at is None:
            return None
        return (datetime.now(timezone.utc) - self.loaded_at).total_seconds()

    # -- price feed --------------------------------------------------------
    def _fetch_price_map(self) -> PriceMap:
        """Day-ahead prices for the period; any failure degrades to no prices.

        The £ valuation is an optional layer: an outage or schema change in
        the market-index endpoint must never take down the dataset itself.
        """
        s = self.settings
        if not s.prices_enabled:
            return {}
        fetch = getattr(self.client, "fetch_prices", None)
        if fetch is None:
            return {}
        try:
            rows = fetch(s.period_start, s.period_end)
        except Exception as exc:  # noqa: BLE001 - degradation is the point
            logger.warning("price feed unavailable, £ valuation disabled: %s", exc)
            return {}
        prices = {(r.settlement_date, r.settlement_period): r.price_gbp_per_mwh for r in rows}
        logger.info("fetched %s day-ahead price points", len(prices))
        return prices

    # -- load paths --------------------------------------------------------
    def load(self) -> None:
        """Live fetch from Elexon (actuals, forecasts, prices) then ingest."""
        s = self.settings
        actuals_raw = self.client.fetch_actuals(s.period_start, s.period_end, self.fuel_type)
        if self.forecast_available:
            forecasts_raw = self.client.fetch_forecasts(
                s.forecast_publish_from, s.forecast_publish_to
            )
        else:
            forecasts_raw = []
            logger.info(
                "fuelType=%s has no WINDFOR counterpart; forecast comparison disabled",
                self.fuel_type,
            )
        logger.info(
            "fetched %s FUELHH rows (fuelType=%s) and %s WINDFOR rows",
            len(actuals_raw),
            self.fuel_type,
            len(forecasts_raw),
        )
        self._ingest(actuals_raw, forecasts_raw, self._fetch_price_map(), source="live fetch")

    def load_snapshot(self, payload: dict) -> None:
        """Cold start from the shipped snapshot file (no network calls)."""
        actuals_raw, forecasts_raw, prices = snapshot_service.decode(payload)
        generated = payload.get("generated_at", "unknown time")
        self._ingest(
            actuals_raw,
            forecasts_raw,
            prices,
            source=f"shipped snapshot (generated {generated}; ?refresh=true fetches live)",
        )

    def _ingest(
        self,
        actuals_raw: list[ActualRow],
        forecasts_raw: list[ForecastRow],
        prices: PriceMap,
        source: str,
    ) -> None:
        """Dedupe, select, align and price-stamp raw rows. Shared by every load path."""
        s = self.settings
        actuals, actual_dupes = dedupe_actuals(actuals_raw)
        forecasts, forecast_dupes = dedupe_forecasts(forecasts_raw)
        selected = select_decision_time_forecasts(
            forecasts, s.decision_cutoff, s.period_start, s.period_end
        )

        actual_by_start = {row.start_time: row for row in actuals}
        self.actual_rows = actuals
        self.forecast_rows = forecasts
        self.selected = selected
        self.prices = prices
        self.hourly = build_hourly_points(
            s.period_start, s.period_end, actual_by_start, selected, prices
        )
        self.halfhourly = build_halfhourly_points(
            s.period_start, s.period_end, actual_by_start, selected, prices
        )
        self.stats = {
            "fuel_type": self.fuel_type,
            "forecast_available": self.forecast_available,
            "source": source,
            "price_points_fetched": len(prices),
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
# One store per fuel type: FUELHH rows differ by fuel and WINDFOR only exists
# for wind, so the datasets can never be mixed inside a single store.
_stores: dict[str, DataStore] = {}
_lock = threading.Lock()


def build_store(settings: Settings, fuel_type: str | None = None) -> DataStore:
    return DataStore(ElexonClient(settings), settings, fuel_type)


def get_store(
    settings: Settings, refresh: bool = False, fuel_type: str | None = None
) -> DataStore:
    """Return the cached store for a fuel type, loading it when absent, stale or refresh=True.

    Cache policy: in-process, one row-set per fuel type for the whole study
    period, TTL = settings.cache_ttl_seconds, forced reload via ?refresh=true.
    No database: the dataset is ~1488 actual + ~18.7k forecast rows.

    Load order for a cold/stale store:
      1. refresh=true -> always a live Elexon fetch (bypasses the snapshot),
      2. otherwise the shipped snapshot when it exists and matches the
         configured period/fuel (the reporting period is closed, so the
         frozen rows are the same rows Elexon would return),
      3. otherwise a live fetch. Any snapshot load failure falls through
         to (3) - the snapshot can only ever make startup faster, never
         change what is served incorrectly.
    """
    fuel = normalize_fuel_type(fuel_type or settings.fuel_type)
    with _lock:
        store = _stores.get(fuel)
        stale = store is None or not store.is_loaded
        if not stale and store is not None:
            stale = (store.age_seconds() or 0) > settings.cache_ttl_seconds
        if refresh or stale:
            store = build_store(settings, fuel)
            payload = None if refresh else snapshot_service.load(settings)
            if payload is not None:
                store.load_snapshot(payload)
            else:
                store.load()  # ElexonError propagates -> 502 handler
            _stores[fuel] = store
        return store


def cache_status(settings: Settings, fuel_type: str | None = None) -> dict:
    fuel = normalize_fuel_type(fuel_type or settings.fuel_type)
    with _lock:
        store = _stores.get(fuel)
        if store is None or not store.is_loaded:
            return {
                "loaded": False,
                "ttl_seconds": settings.cache_ttl_seconds,
                "source": "not loaded",
            }
        return {
            "loaded": True,
            "loaded_at": store.loaded_at,
            "age_seconds": round(store.age_seconds() or 0, 1),
            "ttl_seconds": settings.cache_ttl_seconds,
            "source": str(store.stats.get("source", "live fetch")),
        }


def reset_cache() -> None:
    """Test hook."""
    with _lock:
        _stores.clear()
