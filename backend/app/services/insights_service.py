"""Deterministic, evidence-based insights over a served interval range.

Rules:
  * Every insight is computed from the same matched interval set used by
    metrics_service (selection rules applied upstream).
  * Each insight carries the numbers that produced it (finding + evidence).
  * Language is observational; no causal claims about time-of-day or
    weather patterns.
  * When the range lacks the data an insight needs, the insight is
    returned with available=False and an explicit reason (never invented).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timezone
from typing import Sequence

from app.models.records import IntervalPoint, STATUS_MATCHED
from app.models.schemas import Grain, InsightItem

_UNAVAILABLE_NO_MATCHED = "No matched forecast/actual intervals in the selected range."


def _fmt_mw(value: float) -> str:
    return f"{value:,.1f} MW"


def _daily_mae(matched: Sequence[IntervalPoint]) -> dict[date, float]:
    by_day: dict[date, list[float]] = defaultdict(list)
    for p in matched:
        if p.actual_mw is not None and p.forecast_mw is not None:
            by_day[p.settlement_date].append(abs(p.forecast_mw - p.actual_mw))
    return {day: sum(vals) / len(vals) for day, vals in by_day.items() if vals}


def build_insights(
    points: Sequence[IntervalPoint],
    start: date,
    end: date,
    grain: Grain,
    expected_count: int,
) -> list[InsightItem]:
    period = f"{start.isoformat()} to {end.isoformat()} (UTC delivery dates)"
    matched = [
        p
        for p in points
        if p.status == STATUS_MATCHED and p.actual_mw is not None and p.forecast_mw is not None
    ]
    insights: list[InsightItem] = []

    # 1. Bias direction over the period -------------------------------------
    if matched:
        errors = [p.forecast_mw - p.actual_mw for p in matched]  # type: ignore[operator]
        bias = sum(errors) / len(errors)
        if abs(bias) < 1.0:
            direction = "broadly balanced (mean signed error within +/-1 MW)"
        elif bias > 0:
            direction = f"on average { _fmt_mw(abs(bias)) } too high (over-forecast)"
        else:
            direction = f"on average { _fmt_mw(abs(bias)) } too low (under-forecast)"
        insights.append(
            InsightItem(
                id="bias_direction",
                finding=f"Forecast generation was {direction} across the period.",
                evidence=(
                    f"Mean signed error (forecast - actual) = {bias:+,.1f} MW over "
                    f"{len(matched)} matched intervals."
                ),
                period=period,
                why_it_matters=(
                    "A persistent bias direction indicates which way the decision-time "
                    "forecast tends to err in this sample; it is a historical average, "
                    "not a future expectation."
                ),
            )
        )
    else:
        insights.append(
            InsightItem(
                id="bias_direction",
                finding="Bias direction unavailable.",
                evidence="",
                period=period,
                why_it_matters="Bias requires matched forecast and actual intervals.",
                available=False,
                unavailable_reason=_UNAVAILABLE_NO_MATCHED,
            )
        )

    # 2. Coverage ------------------------------------------------------------
    coverage = (100.0 * len(matched) / expected_count) if expected_count else 0.0
    n_missing_actual = sum(
        1 for p in points if p.status in ("forecast_only", "missing_both")
    )
    n_missing_forecast = sum(
        1 for p in points if p.status in ("actual_only", "missing_both")
    )
    insights.append(
        InsightItem(
            id="coverage",
            finding=(
                f"{len(matched)} of {expected_count} expected intervals were matched "
                f"({coverage:.1f}% coverage)."
            ),
            evidence=(
                f"Missing actual: {n_missing_actual}. Missing forecast: "
                f"{n_missing_forecast}. Metrics are computed over matched intervals only."
            ),
            period=period,
            why_it_matters=(
                "Coverage states how much of the requested range the error statistics "
                "actually rest on; incomplete coverage is never reported as complete."
            ),
        )
    )

    # 3. Day with the highest MAE -------------------------------------------
    daily = _daily_mae(matched)
    if daily:
        worst_day, worst_mae = max(daily.items(), key=lambda kv: kv[1])
        worst_n = sum(1 for p in matched if p.settlement_date == worst_day)
        insights.append(
            InsightItem(
                id="worst_mae_day",
                finding=f"{worst_day.isoformat()} had the highest daily MAE of the period.",
                evidence=(
                    f"Daily MAE = {_fmt_mw(worst_mae)} over {worst_n} matched intervals "
                    f"on that date; computed from hourly/half-hourly points at the "
                    f"requested grain ({grain})."
                ),
                period=period,
                why_it_matters=(
                    "Identifies the date carrying the largest average absolute miss, "
                    "so it can be inspected first; it does not explain why the error "
                    "was larger that day."
                ),
            )
        )
        if len(daily) >= 2:
            best_day, best_mae = min(daily.items(), key=lambda kv: kv[1])
            insights.append(
                InsightItem(
                    id="daily_mae_spread",
                    finding=(
                        f"Daily MAE ranged from {_fmt_mw(best_mae)} on "
                        f"{best_day.isoformat()} to {_fmt_mw(worst_mae)} on "
                        f"{worst_day.isoformat()}."
                    ),
                    evidence=(
                        f"Spread between best and worst matched day = "
                        f"{_fmt_mw(worst_mae - best_mae)} across {len(daily)} days "
                        f"with matched data."
                    ),
                    period=period,
                    why_it_matters=(
                        "Shows how much day-to-day accuracy varies within the sample; "
                        "a single average hides this variation."
                    ),
                )
            )
        else:
            insights.append(
                InsightItem(
                    id="daily_mae_spread",
                    finding="Daily MAE spread unavailable.",
                    evidence="",
                    period=period,
                    why_it_matters="Needs matched intervals on at least two distinct dates.",
                    available=False,
                    unavailable_reason="Fewer than two dates with matched data in this range.",
                )
            )
    else:
        insights.append(
            InsightItem(
                id="worst_mae_day",
                finding="Worst-MAE day unavailable.",
                evidence="",
                period=period,
                why_it_matters="Needs matched intervals to compute a daily MAE.",
                available=False,
                unavailable_reason=_UNAVAILABLE_NO_MATCHED,
            )
        )

    # 4. Largest single-interval absolute error ------------------------------
    if matched:
        largest = max(
            matched, key=lambda p: abs((p.forecast_mw or 0) - (p.actual_mw or 0))
        )
        err = largest.forecast_mw - largest.actual_mw  # type: ignore[operator]
        ts = largest.timestamp.astimezone(timezone.utc)
        insights.append(
            InsightItem(
                id="largest_abs_error",
                finding=(
                    f"Largest single-interval absolute error: "
                    f"{_fmt_mw(abs(err))} at {ts.strftime('%Y-%m-%d %H:%M')} UTC."
                ),
                evidence=(
                    f"Forecast {_fmt_mw(largest.forecast_mw or 0)} vs actual "
                    f"{_fmt_mw(largest.actual_mw or 0)} (signed error "
                    f"{err:+,.1f} MW; positive = over-forecast)."
                ),
                period=period,
                why_it_matters=(
                    "The worst single interval drives RMSE and is the natural first "
                    "candidate for case-by-case inspection."
                ),
            )
        )
    else:
        insights.append(
            InsightItem(
                id="largest_abs_error",
                finding="Largest-error interval unavailable.",
                evidence="",
                period=period,
                why_it_matters="Needs at least one matched interval.",
                available=False,
                unavailable_reason=_UNAVAILABLE_NO_MATCHED,
            )
        )

    # 5. Error concentration: p90 vs MAE (historical statistic) -------------
    if len(matched) >= 10:
        abs_errs = sorted(
            abs(p.forecast_mw - p.actual_mw) for p in matched  # type: ignore[operator]
        )
        p90 = abs_errs[max(1, math.ceil(0.9 * len(abs_errs))) - 1]
        mae = sum(abs_errs) / len(abs_errs)
        insights.append(
            InsightItem(
                id="error_concentration",
                finding=(
                    f"The largest 10% of interval errors reach {_fmt_mw(p90)} or more, "
                    f"vs an average absolute error of {_fmt_mw(mae)}."
                ),
                evidence=(
                    f"p90 (nearest-rank) of |error| = {_fmt_mw(p90)} over "
                    f"{len(matched)} matched intervals. Historical error statistic, "
                    f"not a calibrated confidence bound."
                ),
                period=period,
                why_it_matters=(
                    "RMSE/MAE averages hide tail misses; the gap between p90 and MAE "
                    "shows how concentrated the large errors are."
                ),
            )
        )
    else:
        insights.append(
            InsightItem(
                id="error_concentration",
                finding="Error concentration unavailable.",
                evidence="",
                period=period,
                why_it_matters="Needs at least 10 matched intervals for a stable p90.",
                available=False,
                unavailable_reason="Fewer than 10 matched intervals in this range.",
            )
        )

    return insights
