"""Accuracy metrics over matched intervals only.

Rules:
  * Metrics use intervals where BOTH forecast and actual exist (status == matched).
  * Coverage = matched / expected is always reported alongside the metrics;
    incomplete coverage is never presented as 100%.
  * MAPE excludes matched intervals whose actual value is 0 (undefined ratio);
    the exclusion count is reported (`mape_excluded_intervals`).
  * When there are no matched intervals the metric values are null, never 0.
  * bias = mean(forecast - actual): positive = over-forecast.
  * £ valuation is indicative: matched intervals priced at the day-ahead
    market-index price (APXMIDP); unpriced intervals are excluded from the
    money totals and the price coverage is reported next to them. It is not
    an imbalance settlement figure.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from app.models.records import IntervalPoint, STATUS_MATCHED
from app.models.schemas import AccuracyStats

PRICE_SOURCE_TEXT = (
    "Elexon market-index day-ahead mid price (APXMIDP, £/MWh)"
)


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _median(values: Sequence[float]) -> float | None:
    """Median; null for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _p90_nearest_rank(values: Sequence[float]) -> float | None:
    """90th percentile, nearest-rank (ceil(0.9*n)-th smallest).

    Null when the sample is empty. Callers enforce the minimum sample
    size for reporting. Historical error statistic, not a confidence bound.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(0.9 * len(ordered))
    rank = max(1, min(rank, len(ordered)))
    return ordered[rank - 1]


P90_MIN_MATCHED = 10


def _cost(
    matched: Sequence[IntervalPoint],
) -> tuple[int, float | None, float | None]:
    """Indicative £ value of the error over matched intervals with a price.

    Returns (n_priced, net_value_gbp, absolute_value_gbp); both money values
    are null when nothing is priced - never 0, which would read as "no error".
    net = sum(error x price x hours), absolute = sum(|error| x price x hours).
    """
    priced = [p for p in matched if p.price_gbp_per_mwh is not None]
    if not priced:
        return 0, None, None
    net = sum(
        (p.forecast_mw - p.actual_mw) * p.price_gbp_per_mwh * p.duration_hours  # type: ignore[operator]
        for p in priced
    )
    absolute = sum(
        abs(p.forecast_mw - p.actual_mw) * p.price_gbp_per_mwh * p.duration_hours  # type: ignore[operator]
        for p in priced
    )
    return len(priced), round(net, 2), round(absolute, 2)


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

    abs_errors = [abs(e) for e in errors]
    median_abs = _median(abs_errors)
    p90_abs = _p90_nearest_rank(abs_errors) if n_matched >= P90_MIN_MATCHED else None

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
    n_missing_actual = status_counts["forecast_only"] + status_counts["missing_both"]
    n_missing_forecast = status_counts["actual_only"] + status_counts["missing_both"]

    avg_forecast = _mean([p.forecast_mw for p in matched])
    avg_actual = _mean([p.actual_mw for p in matched])

    n_priced, net_value, abs_value = _cost(matched)
    price_coverage = (100.0 * n_priced / n_matched) if n_matched else 0.0

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
        median_abs_error_mw=round(median_abs, 3) if median_abs is not None else None,
        p90_abs_error_mw=round(p90_abs, 3) if p90_abs is not None else None,
        n_missing_actual=n_missing_actual,
        n_missing_forecast=n_missing_forecast,
        avg_forecast_mw=round(avg_forecast, 3) if avg_forecast is not None else None,
        avg_actual_mw=round(avg_actual, 3) if avg_actual is not None else None,
        status_counts=status_counts,
        n_priced_intervals=n_priced,
        price_coverage_pct=round(price_coverage, 2),
        net_error_value_gbp=net_value,
        abs_error_value_gbp=abs_value,
        price_source=PRICE_SOURCE_TEXT if n_priced else None,
    )
