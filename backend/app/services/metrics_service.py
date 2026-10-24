"""Accuracy metrics over matched intervals only.

Rules:
  * Metrics use intervals where BOTH forecast and actual exist (status == matched).
  * Coverage = matched / expected is always reported alongside the metrics;
    incomplete coverage is never presented as 100%.
  * MAPE excludes matched intervals whose actual value is 0 (undefined ratio);
    the exclusion count is reported (`mape_excluded_intervals`).
  * When there are no matched intervals the metric values are null, never 0.
  * bias = mean(forecast - actual): positive = over-forecast.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from app.models.records import IntervalPoint, STATUS_MATCHED
from app.models.schemas import AccuracyStats


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def compute_stats(points: Sequence[IntervalPoint], expected_count: int, grain: str) -> AccuracyStats:
    counts = Counter(p.status for p in points)
    matched = [
        p
        for p in points
        if p.status == STATUS_MATCHED and p.actual_mw is not None and p.forecast_mw is not None
    ]
    n_matched = len(matched)
    n_expected = expected_count
    n_missing = max(0, n_expected - n_matched)
    coverage = (100.0 * n_matched / n_expected) if n_expected else 0.0

    errors = [p.forecast_mw - p.actual_mw for p in matched]  # type: ignore[operator]
    mae = _mean([abs(e) for e in errors])
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None
    bias = _mean(errors)

    pct_errors = [
        abs(p.forecast_mw - p.actual_mw) / abs(p.actual_mw)  # type: ignore[operator]
        for p in matched
        if p.actual_mw != 0
    ]
    mape = (sum(pct_errors) / len(pct_errors) * 100.0) if pct_errors else None
    mape_excluded = n_matched - len(pct_errors)

    status_counts = {
        "matched": counts.get("matched", 0),
        "forecast_only": counts.get("forecast_only", 0),
        "actual_only": counts.get("actual_only", 0),
        "missing_both": counts.get("missing_both", 0),
    }

    avg_forecast = _mean([p.forecast_mw for p in matched])
    avg_actual = _mean([p.actual_mw for p in matched])

    return AccuracyStats(
        grain=grain,  # type: ignore[arg-type]
        n_expected=n_expected,
        n_matched=n_matched,
        n_missing=n_missing,
        coverage_pct=round(coverage, 2),
        coverage_complete=n_matched == n_expected and n_expected > 0,
        mae_mw=round(mae, 3) if mae is not None else None,
        rmse_mw=round(rmse, 3) if rmse is not None else None,
        bias_mw=round(bias, 3) if bias is not None else None,
        mape_pct=round(mape, 3) if mape is not None else None,
        mape_excluded_intervals=mape_excluded,
        avg_forecast_mw=round(avg_forecast, 3) if avg_forecast is not None else None,
        avg_actual_mw=round(avg_actual, 3) if avg_actual is not None else None,
        status_counts=status_counts,
    )
