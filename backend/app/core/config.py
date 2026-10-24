"""Application settings (env-overridable, no external dependencies)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    base_url: str
    period_start: date
    period_end: date
    decision_cutoff: time  # time of day on D-1, UTC
    cache_ttl_seconds: int
    http_timeout_seconds: float
    http_retries: int

    @property
    def period_days(self) -> int:
        return (self.period_end - self.period_start).days + 1

    @property
    def forecast_publish_from(self) -> datetime:
        # need the D-1 07:30 vintage for the first delivery day
        return datetime.combine(
            self.period_start - timedelta(days=1), time(0, 0), tzinfo=timezone.utc
        )

    @property
    def forecast_publish_to(self) -> datetime:
        return datetime.combine(self.period_end, time(23, 59, 59), tzinfo=timezone.utc)

    @property
    def decision_cutoff_label(self) -> str:
        return self.decision_cutoff.strftime("%H:%M")


def _parse_cutoff(raw: str) -> time:
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("DECISION_CUTOFF_HHMM must look like 'HH:MM'")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("DECISION_CUTOFF_HHMM is not a valid time of day")
    return time(hour, minute)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        base_url=_env("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"),
        period_start=date.fromisoformat(_env("PERIOD_START", "2026-01-01")),
        period_end=date.fromisoformat(_env("PERIOD_END", "2026-01-31")),
        decision_cutoff=_parse_cutoff(_env("DECISION_CUTOFF_HHMM", "09:20")),
        cache_ttl_seconds=int(_env("CACHE_TTL_SECONDS", "3600")),
        http_timeout_seconds=float(_env("ELEXON_TIMEOUT_SECONDS", "60")),
        http_retries=int(_env("ELEXON_RETRIES", "3")),
    )
