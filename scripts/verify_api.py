#!/usr/bin/env python3
"""Phase 1 verification probe for the Elexon BMRS Insights API.

Confirms, against the live API:
  1. FUELHH (actuals) response schema, filters, January 2026 completeness.
  2. WINDFOR (forecasts) response schema, filters, historical vintage availability.
  3. Publication cadence and coverage window of WINDFOR vintages.
  4. Day-ahead forecast selection rule: latest vintage published at or before
     the decision cutoff (09:20 UTC on D-1) that covers all 24 hours of D.

Run:  python3 scripts/verify_api.py
Exit code 0 = all checks pass, 1 = at least one check failed.
Uses only the Python standard library.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
DECISION_CUTOFF_HOUR = (9, 20)  # 09:20 UTC on D-1, EPEX SPOT GB DA 60-min gate closure
JAN_FIRST = date(2026, 1, 1)
JAN_LAST = date(2026, 1, 31)

_failures: list[str] = []


def check(condition: bool, message: str) -> None:
    status = "PASS" if condition else "FAIL"
    if not condition:
        _failures.append(message)
    print(f"[{status}] {message}")


def get_json(path: str, params: dict) -> object:
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{BASE_URL}{path}?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} for {url}\n{body}") from exc


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_actuals() -> list[dict]:
    return get_json(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": JAN_FIRST.isoformat(),
            "settlementDateTo": JAN_LAST.isoformat(),
            "fuelType": "WIND",
        },
    )


def fetch_forecasts() -> list[dict]:
    return get_json(
        "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": "2025-12-31T00:00:00Z",
            "publishDateTimeTo": "2026-02-01T00:00:00Z",
        },
    )


def verify_actuals_schema(rows: list[dict]) -> None:
    required = {"dataset", "publishTime", "startTime", "settlementDate",
                "settlementPeriod", "fuelType", "generation"}
    check(bool(rows), "FUELHH returned rows")
    check(all(required <= set(r) for r in rows), "FUELHH rows match documented schema")
    check(all(r["dataset"] == "FUELHH" for r in rows), "FUELHH dataset field is FUELHH")
    check(all(r["fuelType"] == "WIND" for r in rows), "fuelType filter returns WIND only")


def verify_actuals_completeness(rows: list[dict]) -> None:
    expected = 31 * 48
    check(len(rows) == expected, f"FUELHH row count {len(rows)} == 31 days x 48 SP ({expected})")
    keys = [(r["settlementDate"], r["settlementPeriod"]) for r in rows]
    dupes = [k for k, v in Counter(keys).items() if v > 1]
    check(not dupes, f"FUELHH has no duplicate settlement periods (dupes: {len(dupes)})")
    check(all(r["generation"] is not None for r in rows), "FUELHH has no null generation values")
    check(all(r["generation"] >= 0 for r in rows), "FUELHH has no negative generation values")
    per_day = Counter(r["settlementDate"] for r in rows)
    bad_days = [d for d, n in per_day.items() if n != 48]
    check(not bad_days, f"every January day has 48 settlement periods (bad: {bad_days})")
    sp_values = {r["settlementPeriod"] for r in rows}
    check(sp_values == set(range(1, 49)), "settlementPeriod values are 1..48")
    print(f"       FUELHH MW range: {min(r['generation'] for r in rows)}"
          f"-{max(r['generation'] for r in rows)}")


def verify_forecast_schema(rows: list[dict]) -> None:
    required = {"dataset", "publishTime", "startTime", "generation"}
    check(bool(rows), "WINDFOR returned rows")
    check(all(required <= set(r) for r in rows), "WINDFOR rows match documented schema")
    check(all(r["dataset"] == "WINDFOR" for r in rows), "WINDFOR dataset field is WINDFOR")
    check(all(r["startTime"][14:16] == "00" for r in rows),
          "WINDFOR startTime is hourly (minute == 00)")
    check(all(r["publishTime"].endswith("Z") and r["startTime"].endswith("Z") for r in rows),
          "WINDFOR timestamps are UTC (Z suffix)")
    keys = [(r["publishTime"], r["startTime"]) for r in rows]
    dupes = [k for k, v in Counter(keys).items() if v > 1]
    check(not dupes, f"WINDFOR has no duplicate (publishTime, startTime) keys (dupes: {len(dupes)})")
    check(all(r["generation"] is not None for r in rows), "WINDFOR has no null generation values")
    check(all(r["generation"] >= 0 for r in rows), "WINDFOR has no negative generation values")
    print(f"       WINDFOR MW range: {min(r['generation'] for r in rows)}"
          f"-{max(r['generation'] for r in rows)}")


def verify_vintages(rows: list[dict]) -> dict[str, list[dict]]:
    by_vintage: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_vintage[row["publishTime"]].append(row)

    check(len(by_vintage) == 256, f"256 WINDFOR vintages retrieved ({len(by_vintage)})")
    per_day = Counter(t[:10] for t in by_vintage)
    check(all(v == 8 for v in per_day.values()),
          "exactly 8 vintage publications per day (cadence confirmed)")
    check(all(len(v) == 73 for v in by_vintage.values()),
          "every vintage contains 73 hourly points")

    # Coverage window observed: (publish date - 1) 21:00 -> (publish date + 2) 21:00 UTC
    windows = set()
    for t, items in by_vintage.items():
        starts = sorted(utc(r["startTime"]) for r in items)
        windows.add((starts[0], starts[-1]))
    expected_first = utc("2025-12-30T21:00:00Z")
    expected_last = utc("2026-01-02T21:00:00Z")
    check((expected_first, expected_last) in windows,
          "coverage window = (publish date -1) 21:00 -> (publish date +2) 21:00 UTC")
    return by_vintage


def verify_selection_rule(by_vintage: dict[str, list[dict]]) -> None:
    """Latest vintage with publishTime <= D-1 09:20 UTC covering all 24 hours of D."""
    vintage_times = sorted(by_vintage)
    selected: list[tuple[date, str]] = []
    missing: list[date] = []

    day = JAN_FIRST
    while day <= JAN_LAST:
        cutoff = datetime.combine(day - timedelta(days=1),
                                  time(*DECISION_CUTOFF_HOUR, tzinfo=timezone.utc))
        candidates = []
        for t in vintage_times:
            if utc(t) > cutoff:
                continue
            starts = {utc(r["startTime"]) for r in by_vintage[t]}
            needed = {datetime.combine(day, time(0, tzinfo=timezone.utc)) + timedelta(hours=h)
                      for h in range(24)}
            if needed <= starts:
                candidates.append(t)
        if not candidates:
            missing.append(day)
        else:
            selected.append((day, max(candidates)))
        day += timedelta(days=1)

    check(not missing, f"every delivery day has an eligible vintage (missing: {missing})")
    check(len(selected) == 31, f"31 days selected ({len(selected)})")
    times = Counter(t[11:] for _, t in selected)
    check(set(times) == {"07:30:00Z"},
          f"selected vintage is always 07:30 UTC on D-1 (observed: {dict(times)})")
    check(all((datetime.combine(d - timedelta(days=1), time(0, tzinfo=timezone.utc))).date()
              == utc(t).date() for d, t in selected),
          "selected vintages are published on D-1 (before the cutoff day)")


def verify_filter_validation() -> None:
    """FUELHH rejects mixing settlementDate and publishDateTime filters (documented 400)."""
    url = (f"{BASE_URL}/datasets/FUELHH/stream?"
           + urllib.parse.urlencode({
               "settlementDateFrom": "2026-01-15",
               "settlementDateTo": "2026-01-15",
               "publishDateTimeFrom": "2026-01-15T00:00:00Z",
               "publishDateTimeTo": "2026-01-16T00:00:00Z",
           }))
    try:
        urllib.request.urlopen(urllib.request.Request(url), timeout=60)
        check(False, "FUELHH rejects mixed settlement/publish filters with HTTP 400")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        check(exc.code == 400 and "cannot be set when a Publish Date" in body,
              "FUELHH rejects mixed settlement/publish filters with HTTP 400")


def main() -> int:
    print("Fetching FUELHH actuals (Jan 2026, fuelType=WIND)...")
    actuals = fetch_actuals()
    verify_actuals_schema(actuals)
    verify_actuals_completeness(actuals)

    print("Fetching WINDFOR forecast vintages (2025-12-31 to 2026-02-01)...")
    forecasts = fetch_forecasts()
    verify_forecast_schema(forecasts)
    by_vintage = verify_vintages(forecasts)
    verify_selection_rule(by_vintage)
    verify_filter_validation()

    print()
    if _failures:
        print(f"{len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
