"""Point-in-time forecast selection rules (Phase 1, verified 31/31 days)."""
from datetime import date, datetime, time, timezone

from tests.conftest import dt, make_forecast
from app.services.forecast_service import decision_cutoff_for, select_decision_time_forecasts

UTC = timezone.utc

PERIOD = (date(2026, 1, 1), date(2026, 1, 31))
CUTOFF = time(9, 20)


def select(rows, cutoff=CUTOFF):
    return select_decision_time_forecasts(rows, cutoff, *PERIOD)


def test_selects_latest_vintage_published_before_cutoff():
    delivery = dt(15, 10)  # 2026-01-15 10:00
    older = make_forecast(dt(14, 7, 30), delivery, 5000)
    newer = make_forecast(dt(14, 9, 15), delivery, 6000)  # 09:15 <= 09:20 cutoff
    chosen = select([older, newer])
    assert chosen[delivery].generation_mw == 6000
    assert chosen[delivery].publish_time == dt(14, 9, 15)


def test_excludes_vintage_published_after_cutoff():
    delivery = dt(15, 10)
    post_cutoff = make_forecast(dt(14, 9, 30), delivery, 7000)  # 09:30 > 09:20 cutoff
    chosen = select([post_cutoff])
    assert delivery not in chosen


def test_cutoff_wins_over_newer_value():
    """A better-looking post-cutoff forecast must never be selected."""
    delivery = dt(15, 10)
    eligible = make_forecast(dt(14, 7, 30), delivery, 5000)
    post = make_forecast(dt(14, 9, 30), delivery, 9999)
    chosen = select([eligible, post])
    assert chosen[delivery].generation_mw == 5000


def test_cutoff_is_specific_to_delivery_day():
    """A vintage from the delivery day itself is after the D-1 cutoff."""
    delivery = dt(15, 10)
    same_day = make_forecast(dt(15, 7, 30), delivery, 8000)
    chosen = select([same_day])
    assert delivery not in chosen


def test_prefers_newest_among_same_day_eligible_vintages():
    """Both vintages on D-1 before the 09:20 cutoff: the newer one wins."""
    delivery = dt(2, 10)
    v1 = make_forecast(dt(1, 2, 30), delivery, 100)
    v2 = make_forecast(dt(1, 7, 30), delivery, 200)
    chosen = select([v1, v2])
    assert chosen[delivery].generation_mw == 200
    assert chosen[delivery].publish_time == dt(1, 7, 30)


def test_later_same_day_vintage_after_cutoff_is_ignored():
    """02:30 and 07:30 eligible; 22:30 on D-1 is after the cutoff -> never wins."""
    delivery = dt(2, 10)
    early = make_forecast(dt(1, 7, 30), delivery, 200)
    late = make_forecast(dt(1, 22, 30), delivery, 999)
    chosen = select([early, late])
    assert chosen[delivery].generation_mw == 200


def test_intervals_outside_period_are_ignored():
    outside = make_forecast(dt(1, 7, 30), datetime(2025, 12, 31, 12, tzinfo=UTC), 100)
    assert select([outside]) == {}


def test_original_publication_time_is_preserved():
    delivery = dt(15, 10)
    row = make_forecast(dt(14, 7, 30), delivery, 4242)
    chosen = select([row])
    assert chosen[delivery].publish_time == dt(14, 7, 30)


def test_decision_cutoff_for_uses_previous_day():
    assert decision_cutoff_for(dt(15, 0), CUTOFF) == dt(14, 9, 20)
    assert decision_cutoff_for(dt(1, 23, 59), CUTOFF).date() == date(2025, 12, 31)
