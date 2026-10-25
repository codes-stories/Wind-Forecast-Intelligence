"""Cold-start snapshot: raw rows shipped with the build, served without network.

The reporting period (January 2026) is closed - its FUELHH actuals, WINDFOR
vintages and day-ahead prices never change - so the dataset can be frozen into
a gzip JSON file that the serverless cold start reads in milliseconds instead
of re-fetching ~20k rows from Elexon. Live fetching stays available:

  * ?refresh=true on any data endpoint always bypasses the snapshot,
  * a missing/invalid/mismatched snapshot falls back to a live fetch,
  * regenerating the file: python scripts/build_snapshot.py

The snapshot is provenance-labelled, never silent: stores.stats["source"]
reports "live fetch" or the snapshot's generation time.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.records import ActualRow, ForecastRow, PriceRow

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1


def _open(path: Path, mode: str):
    if path.name.endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def encode(
    actuals: list[ActualRow],
    forecasts: list[ForecastRow],
    prices: list[PriceRow],
    settings: Settings,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Compact serialisable payload (row arrays, not dicts)."""
    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": _iso(generated),
        "period_start": settings.period_start.isoformat(),
        "period_end": settings.period_end.isoformat(),
        "fuel_type": settings.fuel_type,
        "actuals": [
            [
                r.settlement_date.isoformat(),
                r.settlement_period,
                _iso(r.start_time),
                _iso(r.publish_time),
                r.generation_mw,
            ]
            for r in actuals
        ],
        "forecasts": [
            [_iso(r.publish_time), _iso(r.start_time), r.generation_mw]
            for r in forecasts
        ],
        "prices": [
            [r.settlement_date.isoformat(), r.settlement_period, r.price_gbp_per_mwh]
            for r in prices
        ],
    }


def decode(payload: dict[str, Any]) -> tuple[list[ActualRow], list[ForecastRow], dict[tuple[date, int], float]]:
    """Payload -> raw rows for DataStore._ingest (dedupe/selection still run)."""
    actuals = [
        ActualRow(
            settlement_date=date.fromisoformat(row[0]),
            settlement_period=int(row[1]),
            start_time=datetime.fromisoformat(row[2].replace("Z", "+00:00")),
            publish_time=datetime.fromisoformat(row[3].replace("Z", "+00:00")),
            generation_mw=row[4],
        )
        for row in payload.get("actuals", [])
    ]
    forecasts = [
        ForecastRow(
            publish_time=datetime.fromisoformat(row[0].replace("Z", "+00:00")),
            start_time=datetime.fromisoformat(row[1].replace("Z", "+00:00")),
            generation_mw=row[2],
        )
        for row in payload.get("forecasts", [])
    ]
    prices = {
        (date.fromisoformat(row[0]), int(row[1])): float(row[2])
        for row in payload.get("prices", [])
    }
    return actuals, forecasts, prices


def load(settings: Settings) -> dict[str, Any] | None:
    """Read and validate the snapshot; None when it must not be served.

    None means: file missing, unreadable, wrong version, or built for a
    different reporting period/fuel - the caller then does a live fetch.
    """
    if not settings.snapshot_enabled:
        return None
    path = Path(settings.snapshot_path)
    if not path.is_file():
        logger.info("snapshot not found at %s; a live fetch will be used", path)
        return None
    try:
        with _open(path, "rt") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning("snapshot %s unreadable (%s); falling back to a live fetch", path, exc)
        return None
    if not isinstance(payload, dict) or payload.get("version") != SNAPSHOT_VERSION:
        logger.warning("snapshot %s has an unsupported version; live fetch will be used", path)
        return None
    if payload.get("period_start") != settings.period_start.isoformat() or (
        payload.get("period_end") != settings.period_end.isoformat()
    ):
        logger.warning(
            "snapshot %s covers %s..%s, not the configured %s..%s; live fetch will be used",
            path,
            payload.get("period_start"),
            payload.get("period_end"),
            settings.period_start,
            settings.period_end,
        )
        return None
    if payload.get("fuel_type") != settings.fuel_type:
        logger.warning(
            "snapshot %s is for fuelType=%s, not %s; live fetch will be used",
            path,
            payload.get("fuel_type"),
            settings.fuel_type,
        )
        return None
    return payload


def save(payload: dict[str, Any], settings: Settings) -> Path | None:
    """Best-effort write (used by scripts/build_snapshot.py); None on failure."""
    try:
        path = Path(settings.snapshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _open(path, "wt") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        return path
    except OSError as exc:
        logger.warning("could not write snapshot: %s", exc)
        return None
