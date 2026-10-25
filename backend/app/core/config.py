"""Application settings (env-overridable, no external dependencies)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _parse_bool(raw: str) -> bool:
    """Truthy env parsing: 1/true/yes/on enable; anything else disables."""
    return raw.strip().lower() in ("1", "true", "yes", "on")


# FUELHH fuel types observed upstream (verified against the live stream).
FUEL_TYPES = (
    "BIOMASS",
    "CCGT",
    "COAL",
    "INTELEC",
    "INTEW",
    "INTFR",
    "INTGRNL",
    "INTIFA2",
    "INTIRL",
    "INTNED",
    "INTNEM",
    "INTNSL",
    "INTVKL",
    "NPSHYD",
    "NUCLEAR",
    "OCGT",
    "OIL",
    "OTHER",
    "PS",
    "WIND",
)


# Always allowed by CORS regardless of ALLOWED_ORIGINS: the Vite dev server
# and the deployed Vercel frontend. The env var EXTENDS this list (it never
# replaces it), so a stale or empty value in the deploy dashboard cannot
# break the live app.
FALLBACK_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://wind-forecast-intelligence-rho.vercel.app",
)

# Cold-start snapshot shipped with the build (backend/data/snapshot.json.gz).
# Resolved relative to this file so it works from any working directory
# (repo root, backend/, Vercel's /backend root, the Docker image).
DEFAULT_SNAPSHOT_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "snapshot.json.gz"
)


def normalize_fuel_type(raw: str) -> str:
    """Uppercase and validate a FUELHH fuel type.

    Upstream returns HTTP 200 with an empty array for an unknown fuelType,
    which would silently serve an empty dataset, so the value is rejected here.
    """
    fuel = (raw or "").strip().upper()
    if fuel not in FUEL_TYPES:
        raise ValueError(
            f"unknown fuel type {raw!r}; expected one of {', '.join(FUEL_TYPES)}"
        )
    return fuel


@dataclass(frozen=True)
class Settings:
    base_url: str
    period_start: date
    period_end: date
    decision_cutoff: time  # time of day on D-1, UTC
    cache_ttl_seconds: int
    http_timeout_seconds: float
    http_retries: int
    # Origins always allowed by CORS (see FALLBACK_ORIGINS); the
    # ALLOWED_ORIGINS env var extends this list, it never replaces it.
    allowed_origins: tuple[str, ...] = FALLBACK_ORIGINS
    # FUELHH fuel filter: env default, overridable per request via ?fuel_type=
    fuel_type: str = "WIND"
    # Cold-start snapshot: when enabled and the file exists, the dataset is
    # served from the shipped snapshot instead of re-fetching from Elexon
    # (?refresh=true always forces a live fetch).
    snapshot_enabled: bool = True
    snapshot_path: str = DEFAULT_SNAPSHOT_PATH
    # Day-ahead price feed (£ valuation of forecast error). Failure or a
    # disabled feed degrades to null £ values, never breaks the dataset.
    prices_enabled: bool = True

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


def _parse_origins(raw: str) -> tuple[str, ...]:
    origins = tuple(o.strip() for o in raw.split(",") if o.strip())
    # An empty/whitespace env value is treated as "not set" rather than an
    # error, so a blank ALLOWED_ORIGINS cannot lock every origin out.
    return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # FALLBACK_ORIGINS always win; ALLOWED_ORIGINS only adds more origins.
    env_origins = _parse_origins(_env("ALLOWED_ORIGINS", ""))
    allowed = tuple(dict.fromkeys(FALLBACK_ORIGINS + env_origins))
    return Settings(
        base_url=_env("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"),
        period_start=date.fromisoformat(_env("PERIOD_START", "2026-01-01")),
        period_end=date.fromisoformat(_env("PERIOD_END", "2026-01-31")),
        decision_cutoff=_parse_cutoff(_env("DECISION_CUTOFF_HHMM", "09:20")),
        cache_ttl_seconds=int(_env("CACHE_TTL_SECONDS", "3600")),
        http_timeout_seconds=float(_env("ELEXON_TIMEOUT_SECONDS", "60")),
        http_retries=int(_env("ELEXON_RETRIES", "3")),
        allowed_origins=allowed,
        fuel_type=normalize_fuel_type(_env("FUEL_TYPE", "WIND")),
        snapshot_enabled=_parse_bool(_env("SNAPSHOT_ENABLED", "1")),
        snapshot_path=_env("SNAPSHOT_PATH", DEFAULT_SNAPSHOT_PATH),
        prices_enabled=_parse_bool(_env("PRICES_ENABLED", "1")),
    )
