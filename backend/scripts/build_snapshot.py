#!/usr/bin/env python3
"""Regenerate the cold-start snapshot (backend/data/snapshot.json.gz).

Fetches the full reporting period from Elexon once - actuals, WINDFOR
vintages and day-ahead prices - and freezes it into the gzip JSON file the
serverless cold start serves without any network call. Run this after a
period change or whenever you want to refresh the frozen rows:

    cd backend && python scripts/build_snapshot.py

The file is committed to the repo so Vercel's deployment ships with it.
Live data is still one request away: any endpoint accepts ?refresh=true.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services import snapshot_service  # noqa: E402
from app.services.elexon_client import ElexonClient  # noqa: E402


def main() -> int:
    settings = get_settings()
    client = ElexonClient(settings)
    print(
        f"fetching {settings.period_start}..{settings.period_end} "
        f"(fuelType={settings.fuel_type}) from {settings.base_url}"
    )
    actuals = client.fetch_actuals(settings.period_start, settings.period_end, settings.fuel_type)
    print(f"  FUELHH actuals: {len(actuals)} rows")
    forecasts = client.fetch_forecasts(settings.forecast_publish_from, settings.forecast_publish_to)
    print(f"  WINDFOR forecasts: {len(forecasts)} rows")
    prices = client.fetch_prices(settings.period_start, settings.period_end)
    print(f"  market-index prices: {len(prices)} rows")

    payload = snapshot_service.encode(actuals, forecasts, prices, settings)
    path = snapshot_service.save(payload, settings)
    if path is None:
        print("ERROR: could not write the snapshot file", file=sys.stderr)
        return 1
    size = path.stat().st_size / 1024
    print(f"wrote {path} ({size:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
