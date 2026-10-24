#!/usr/bin/env python3
"""Fetch verified Phase 1 sample records from the Elexon BMRS Insights API.

Writes to data/samples/:
  fuelhh_2026-01-15_wind.json          48 half-hourly actual rows (delivery day example)
  windfor_vintage_2026-01-14T0730Z.json  eligible D-1 07:30 vintage (selected by the rule)
  windfor_vintage_2026-01-14T0930Z.json  post-cutoff vintage (ineligible example)
  manifest.json                          provenance: URLs, fetched_at, row counts, checks

Run:  python3 scripts/fetch_samples.py   (stdlib only)
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def get(path: str, **params) -> tuple[list | dict, str]:
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{path}?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8")), url


def save(name: str, payload) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {name} ({len(payload) if isinstance(payload, list) else 'object'}) rows")


def main() -> None:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    actuals, url_actual = get(
        "/datasets/FUELHH/stream",
        settlementDateFrom="2026-01-15",
        settlementDateTo="2026-01-15",
        fuelType="WIND",
    )
    save("fuelhh_2026-01-15_wind.json", actuals)

    vintages = {}
    for label, stamp in [("0730", "2026-01-14T07:30:00Z"), ("0930", "2026-01-14T09:30:00Z")]:
        rows, url = get(
            "/datasets/WINDFOR/stream",
            publishDateTimeFrom=stamp,
            publishDateTimeTo=stamp[:17] + "59Z",
        )
        vintages[label] = (rows, url, stamp)
        save(f"windfor_vintage_2026-01-14T{label}Z.json", rows)

    # integrity checks recorded in the manifest
    forecast_day = [r for r in vintages["0730"][0]
                    if r["startTime"].startswith("2026-01-15")]
    actual_keys = {(r["settlementDate"], r["settlementPeriod"]) for r in actuals}
    checks = {
        "actual_rows_is_48": len(actuals) == 48,
        "actual_unique_settlement_periods": len(actual_keys) == 48,
        "actual_no_nulls": all(r["generation"] is not None for r in actuals),
        "eligible_vintage_rows": len(vintages["0730"][0]),
        "eligible_vintage_covers_delivery_day_hours": len(forecast_day) == 24,
        "eligible_vintage_publishTime": vintages["0730"][2],
        "post_cutoff_vintage_publishTime": vintages["0930"][2],
        "forecast_rows_on_minute_00_only": all(
            r["startTime"][14:16] == "00"
            for rows, _, _ in vintages.values()
            for r in rows
        ),
    }

    # units scale cross-check (same magnitude => MW for both series, same day)
    actual_mw = sorted(r["generation"] for r in actuals)
    forecast_mw = sorted(r["generation"] for r in forecast_day)
    checks["scale_crosscheck"] = {
        "actual_min_max_mw": [actual_mw[0], actual_mw[-1]],
        "forecast_min_max_mw": [forecast_mw[0], forecast_mw[-1]],
        "note": "same magnitude for the same delivery day; supports the MW assumption",
    }

    manifest = {
        "fetched_at_utc": fetched_at,
        "source": "Elexon Insights (BMRS) API",
        "requests": {
            "actuals": url_actual,
            "eligible_vintage": vintages["0730"][1],
            "post_cutoff_vintage": vintages["0930"][1],
        },
        "decision_cutoff_rule": (
            "Latest WINDFOR vintage with publishTime <= 09:20 UTC on D-1 "
            "(EPEX SPOT GB day-ahead order-book closure) covering all hours of D."
        ),
        "checks": checks,
    }
    save("manifest.json", manifest)
    print(json.dumps(checks, indent=1))
    if not all(v is True for k, v in checks.items() if isinstance(v, bool)):
        raise SystemExit("sample integrity check FAILED")
    print("sample integrity checks PASSED")


if __name__ == "__main__":
    main()
