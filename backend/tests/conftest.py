"""Shared synthetic fixtures. Synthetic records are for unit tests only -
they are NEVER used for production analytics (production loads live Elexon data)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.config import Settings
from app.models.records import ActualRow, ForecastRow
from app.services.forecast_service import DataStore

UTC = timezone.utc


def make_settings(**overrides) -> Settings:
    base = dict(
        base_url="https://unit.test",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        decision_cutoff=time(9, 20),
        cache_ttl_seconds=3600,
        http_timeout_seconds=5.0,
        http_retries=1,
    )
    base.update(overrides)
    return Settings(**base)


def dt(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 1, day, hh, mm, tzinfo=UTC)


def make_actual(day: date, sp: int, mw, publish: datetime | None = None) -> ActualRow:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(minutes=30 * (sp - 1))
    return ActualRow(
        settlement_date=day,
        settlement_period=sp,
        start_time=start,
        publish_time=publish or start + timedelta(minutes=30),
        generation_mw=mw,
    )


def make_forecast(publish: datetime, start: datetime, mw) -> ForecastRow:
    return ForecastRow(publish_time=publish, start_time=start, generation_mw=mw)


class FakeClient:
    """Returns pre-loaded synthetic rows; can simulate upstream failures."""

    def __init__(self, actuals=(), forecasts=(), error: Exception | None = None):
        self.actuals = list(actuals)
        self.forecasts = list(forecasts)
        self.error = error

    def fetch_actuals(self, start: date, end: date) -> list[ActualRow]:
        if self.error is not None:
            raise self.error
        return [r for r in self.actuals if start <= r.settlement_date <= end]

    def fetch_forecasts(self, publish_from: datetime, publish_to: datetime) -> list[ForecastRow]:
        if self.error is not None:
            raise self.error
        return [r for r in self.forecasts if publish_from <= r.publish_time <= publish_to]


def synth_period(
    start: date = date(2026, 1, 1),
    end: date = date(2026, 1, 31),
) -> tuple[list[ActualRow], list[ForecastRow]]:
    """Complete synthetic period: 48 actuals/day, one eligible (07:30 D-1) and one
    post-cutoff (09:30 D-1) vintage per delivery day."""
    actuals: list[ActualRow] = []
    forecasts: list[ForecastRow] = []
    day = start
    while day <= end:
        for sp in range(1, 49):
            actuals.append(make_actual(day, sp, 10000 + sp))  # deterministic, never 0
        prev = day - timedelta(days=1)
        for hour in range(24):
            delivery_hour = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            eligible = datetime(prev.year, prev.month, prev.day, 7, 30, tzinfo=UTC)
            post = datetime(prev.year, prev.month, prev.day, 9, 30, tzinfo=UTC)
            forecasts.append(make_forecast(eligible, delivery_hour, 9000 + hour))
            forecasts.append(make_forecast(post, delivery_hour, 9500 + hour))
        day += timedelta(days=1)
    return actuals, forecasts


def loaded_store(actuals=(), forecasts=(), settings: Settings | None = None) -> DataStore:
    settings = settings or make_settings()
    store = DataStore(FakeClient(actuals, forecasts), settings)
    store.load()
    return store


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def synth_store() -> DataStore:
    actuals, forecasts = synth_period()
    return loaded_store(actuals, forecasts)
