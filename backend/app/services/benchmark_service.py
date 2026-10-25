"""Decision Lab: cutoff sensitivity, envelope calibration, skill vs persistence.

All three are deterministic historical analyses over the already-loaded
dataset - no LLM, no probabilistic model, no new data source:

  * Cutoff sensitivity re-runs the documented selection rule (latest vintage
    published at or before HH:MM on D-1) for candidate cutoff times and
    reports the resulting hourly accuracy. It answers "what would the error
    have been with a different gate?" - a historical what-if, not advice.
  * Calibration checks how often the actual fell inside the min-max envelope
    of the pre-cutoff vintages - a consensus-spread proxy, never presented
    as a calibrated probabilistic forecast.
  * Skill compares MAE against a persistence baseline (the actual at the same
    half-hour 24h earlier) on the common sample where both exist.

Rules inherited from the rest of the app: metrics over matched intervals
only, nulls never 0, bias = forecast - actual, publication times preserved.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from app.core.config import Settings
from app.models.records import STATUS_MATCHED
from app.models.schemas import (
    BenchmarksResponse,
    CalibrationStats,
    CutoffCandidate,
    CutoffSensitivityResponse,
    SkillStats,
)
from app.services import metrics_service
from app.services.forecast_service import (
    build_hourly_points,
    decision_cutoff_for,
    points_in_range,
    select_decision_time_forecasts,
)

# Cap on candidate cutoffs: the configured cutoff plus the most frequent
# publication times-of-day (each WINDFOR day repeats the same schedule).
MAX_CUTOFF_CANDIDATES = 16

CUTOFF_RULE = (
    "Each candidate re-runs the selection rule with that cutoff time on D-1: "
    "latest vintage published at or before the candidate cutoff, then the same "
    "hourly accuracy metrics over matched intervals."
)

CALIBRATION_LIMITATION = (
    "The envelope is the min-max spread of pre-cutoff publications for the hour "
    "(a consensus proxy for uncertainty, not a calibrated probabilistic forecast). "
    "Hours with a single eligible vintage have a zero-width envelope."
)


def _hourly_accuracy(
    store,
    start: date,
    end: date,
    cutoff: time,
) -> tuple[float | None, float | None, float | None, int, float]:
    """(mae, rmse, bias, n_matched, coverage_pct) for one candidate cutoff."""
    winners = select_decision_time_forecasts(store.forecast_rows, cutoff, start, end)
    actual_by_start = {row.start_time: row for row in store.actual_rows}
    points = build_hourly_points(start, end, actual_by_start, winners)
    days = (end - start).days + 1
    stats = metrics_service.compute_stats(points, days * 24, "hourly")
    return (
        stats.mae_mw,
        stats.rmse_mw,
        stats.bias_mw,
        stats.n_matched,
        stats.coverage_pct,
    )


def cutoff_sensitivity(
    store, start: date, end: date, settings: Settings
) -> CutoffSensitivityResponse:
    """Accuracy at candidate decision cutoffs (historical what-if)."""
    if not store.forecast_available or not store.forecast_rows:
        return CutoffSensitivityResponse(
            start=start,
            end=end,
            current_cutoff_utc=settings.decision_cutoff_label,
            candidates=[],
            best_cutoff_utc=None,
            best_delta_mae_mw=None,
            rule=CUTOFF_RULE,
            note="Cutoff sensitivity requires WINDFOR publications for the range.",
            limitation=(
                "No WINDFOR publications cover this dataset, so no cutoff "
                "sensitivity can be computed (never backfilled)."
            ),
        )

    # Candidate cutoffs: distinct publication times-of-day observed for
    # delivery hours in range, plus the configured cutoff, capped to the
    # most frequent times so the chart stays readable.
    counts: Counter[time] = Counter()
    for row in store.forecast_rows:
        if start <= row.start_time.date() <= end:
            counts[row.publish_time.time()] += 1
    current = settings.decision_cutoff
    others = sorted(
        (t for t in counts if t != current), key=lambda t: (-counts[t], t)
    )
    chosen = sorted({current, *others[: MAX_CUTOFF_CANDIDATES - 1]})

    current_stats = _hourly_accuracy(store, start, end, current)
    current_mae = current_stats[0]

    candidates: list[CutoffCandidate] = []
    for cutoff in chosen:
        mae, rmse, bias, n_matched, coverage = _hourly_accuracy(
            store, start, end, cutoff
        )
        delta = (
            round(mae - current_mae, 3)
            if mae is not None and current_mae is not None
            else None
        )
        candidates.append(
            CutoffCandidate(
                cutoff_utc=cutoff.strftime("%H:%M"),
                is_current=cutoff == current,
                mae_mw=mae,
                rmse_mw=rmse,
                bias_mw=bias,
                n_matched=n_matched,
                coverage_pct=coverage,
                delta_mae_mw=delta,
            )
        )

    scored = [c for c in candidates if c.mae_mw is not None]
    best = min(scored, key=lambda c: (c.mae_mw, c.cutoff_utc)) if scored else None
    return CutoffSensitivityResponse(
        start=start,
        end=end,
        current_cutoff_utc=settings.decision_cutoff_label,
        candidates=candidates,
        best_cutoff_utc=best.cutoff_utc if best else None,
        best_delta_mae_mw=best.delta_mae_mw if best else None,
        rule=CUTOFF_RULE,
        note=(
            "Historical what-if over the selected range: later cutoffs admit later "
            "(post-09:20) publications, earlier cutoffs use older vintages. "
            "Lower MAE here means the gate would have been closer to outturn - "
            "it is not a recommendation for the go-forward cutoff."
        ),
        limitation=None,
    )


def calibration(store, start: date, end: date, settings: Settings) -> CalibrationStats:
    """How often the actual lands inside the pre-cutoff vintage envelope."""
    cutoff = settings.decision_cutoff
    eligible: dict[datetime, list[float]] = {}
    for row in store.forecast_rows:
        day = row.start_time.date()
        if day < start or day > end:
            continue
        if row.publish_time > decision_cutoff_for(row.start_time, cutoff):
            continue
        if row.generation_mw is None:
            continue
        eligible.setdefault(row.start_time, []).append(row.generation_mw)

    actuals = {
        p.timestamp: p.actual_mw
        for p in points_in_range(store.hourly, start, end)
        if p.actual_mw is not None
    }
    days = (end - start).days + 1
    hours_total = days * 24

    evaluated = inside = below = above = 0
    widths: list[float] = []
    vintage_counts: list[int] = []
    for hour in range(24):
        for day_offset in range(days):
            ts = datetime.combine(
                start + timedelta(days=day_offset),
                time(hour),
                tzinfo=timezone.utc,
            )
            values = eligible.get(ts)
            actual = actuals.get(ts)
            if not values or actual is None:
                continue
            evaluated += 1
            lo, hi = min(values), max(values)
            if actual < lo:
                below += 1
            elif actual > hi:
                above += 1
            else:
                inside += 1
            widths.append(hi - lo)
            vintage_counts.append(len(values))

    inside_pct = (100.0 * inside / evaluated) if evaluated else None
    avg_width = (sum(widths) / len(widths)) if widths else None
    avg_vintages = (sum(vintage_counts) / len(vintage_counts)) if vintage_counts else None
    return CalibrationStats(
        hours_total=hours_total,
        hours_evaluated=evaluated,
        hours_inside=inside,
        hours_below=below,
        hours_above=above,
        inside_pct=round(inside_pct, 2) if inside_pct is not None else None,
        avg_envelope_width_mw=round(avg_width, 3) if avg_width is not None else None,
        avg_vintages_per_hour=round(avg_vintages, 2) if avg_vintages is not None else None,
        limitation=CALIBRATION_LIMITATION,
    )


def skill_vs_persistence(store, start: date, end: date) -> SkillStats:
    """MAE of WINDFOR vs yesterday's outturn at the same half-hour."""
    note = (
        "Persistence forecast for interval T = the actual at T - 24h (same clock "
        "half-hour, previous day). Skill is computed on the common sample where "
        "both the forecast and the prior-day actual exist; positive means the "
        "forecast beat persistence, negative means it lost to it. Intervals whose "
        "prior-day actual falls outside the dataset (day 1) are excluded and counted."
    )
    actual_by_ts = {
        p.timestamp: p.actual_mw
        for p in store.halfhourly
        if p.actual_mw is not None
    }
    matched = [
        p
        for p in points_in_range(store.halfhourly, start, end)
        if p.status == STATUS_MATCHED and p.actual_mw is not None and p.forecast_mw is not None
    ]
    wf_errors: list[float] = []
    pers_errors: list[float] = []
    unavailable = 0
    for point in matched:
        persistence = actual_by_ts.get(point.timestamp - timedelta(hours=24))
        if persistence is None:
            unavailable += 1
            continue
        wf_errors.append(abs(point.forecast_mw - point.actual_mw))  # type: ignore[operator]
        pers_errors.append(abs(persistence - point.actual_mw))

    wf_mae = (sum(wf_errors) / len(wf_errors)) if wf_errors else None
    pers_mae = (sum(pers_errors) / len(pers_errors)) if pers_errors else None
    skill = None
    if wf_mae is not None and pers_mae is not None and pers_mae > 0:
        skill = round(100.0 * (1.0 - wf_mae / pers_mae), 2)
    return SkillStats(
        grain="halfhourly",
        n_matched=len(matched),
        n_evaluated=len(wf_errors),
        n_persistence_unavailable=unavailable,
        windfor_mae_mw=round(wf_mae, 3) if wf_mae is not None else None,
        persistence_mae_mw=round(pers_mae, 3) if pers_mae is not None else None,
        skill_pct=skill,
        note=note,
    )


def benchmarks(
    store, start: date, end: date, settings: Settings
) -> BenchmarksResponse:
    """Calibration + skill for one request (both share the range/cutoff)."""
    calibration_stats = calibration(store, start, end, settings)
    skill = skill_vs_persistence(store, start, end)
    note = (
        "Both sections are computed from the served dataset for the selected "
        "range; they are historical statistics, not guarantees about future "
        "forecast performance."
    )
    if not store.forecast_available:
        note += (
            " WINDFOR publishes wind only, so this fuel has no forecast to "
            "benchmark (every benchmark is unavailable)."
        )
    elif not store.forecast_rows:
        note += (
            " No WINDFOR publications cover this dataset, so there is no "
            "forecast to benchmark (nothing is ever backfilled)."
        )
    return BenchmarksResponse(
        start=start,
        end=end,
        current_cutoff_utc=settings.decision_cutoff_label,
        calibration=calibration_stats,
        skill=skill,
        note=note,
    )
