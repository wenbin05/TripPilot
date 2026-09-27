from datetime import UTC, date, time

import pytest

from trippilot.domain.live_constraints import (
    InvalidTravelWindow,
    check_entered_estimates,
    resolve_travel_window,
)
from trippilot.domain.live_draft import schedule_draft


def test_all_categories_required_and_explicit_zero_is_not_unknown():
    partial = check_entered_estimates((100, None, 0, 0, 0), 100)
    assert partial.status == "incomplete"
    assert partial.known_subtotal_minor == 100
    assert partial.missing_categories == ("accommodation",)
    assert partial.estimated_total_minor is None and partial.remaining_minor is None
    complete = check_entered_estimates((100, 0, 0, 0, 0), 100)
    assert complete.status == "within_entered_estimate"
    assert complete.estimated_total_minor == 100 and complete.remaining_minor == 0


def test_exact_minor_units_and_no_traveller_multiplication():
    check = check_entered_estimates((101, 202, 303, 404, 505), 1516)
    assert check.estimated_total_minor == 1515
    assert check.remaining_minor == 1
    assert (
        check_entered_estimates((101, 202, 303, 404, 505), 1514).remaining_minor == -1
    )


def test_known_subtotal_already_over_budget_blocks_even_if_incomplete():
    check = check_entered_estimates((101, None, None, None, None), 100)
    assert check.status == "over_entered_estimate"
    assert check.estimated_total_minor is None


@pytest.mark.parametrize("value", [-1, 1.1, True, "100", 1_000_000_000_001])
def test_bad_money_rejected(value):
    with pytest.raises(ValueError):
        check_entered_estimates((value, 0, 0, 0, 0), 100)


def test_all_unknown_does_not_claim_zero_total():
    check = check_entered_estimates((None,) * 5, 100)
    assert check.status == "incomplete" and check.estimated_total_minor is None
    assert len(check.missing_categories) == 5


def test_arrival_departure_buffers_bound_every_stop():
    start, end = date(2026, 10, 10), date(2026, 10, 11)
    window = resolve_travel_window(
        start, end, time(13), time(12), "America/Toronto", 60
    )
    stops = schedule_draft(
        start,
        end,
        time(9),
        "America/Toronto",
        4,
        tuple((60.0,) * 8 for _ in range(8)),
        window,
    )
    assert stops[0].start.hour == 14
    assert stops[-1].day == end and stops[-1].end.hour <= 11
    assert all(
        window.available_from <= s.start < s.end <= window.available_until
        for s in stops
    )


def test_single_day_no_room_for_visit_does_not_relax_boundaries():
    day = date(2026, 10, 10)
    window = resolve_travel_window(
        day, day, time(13), time(15, 30), "America/Toronto", 60
    )
    assert (
        schedule_draft(day, day, time(9), "America/Toronto", 3, ((0.0,),), window) == ()
    )


@pytest.mark.parametrize(
    "arrival,departure,buffer",
    [(time(17), time(9), 0), (time(9), time(9), 0), (time(9), time(11), 60)],
)
def test_reversed_or_exhausted_windows_rejected(arrival, departure, buffer):
    with pytest.raises(InvalidTravelWindow):
        resolve_travel_window(
            date(2026, 10, 10),
            date(2026, 10, 10),
            arrival,
            departure,
            "America/Toronto",
            buffer,
        )


@pytest.mark.parametrize(
    "day,arrival", [(date(2026, 3, 8), time(2, 30)), (date(2026, 11, 1), time(1, 30))]
)
def test_dst_nonexistent_and_ambiguous_times_rejected(day, arrival):
    with pytest.raises(InvalidTravelWindow, match="clock change"):
        resolve_travel_window(day, day, arrival, time(17), "America/Toronto", 0)


def test_buffers_are_elapsed_minutes_across_dst_transition():
    day = date(2026, 3, 8)
    window = resolve_travel_window(
        day, day, time(1, 30), time(17), "America/Toronto", 60
    )
    assert window.available_from.hour == 3 and window.available_from.minute == 30
    assert (
        window.available_from.astimezone(UTC) - window.arrival.astimezone(UTC)
    ).total_seconds() == 3600


def test_cross_midnight_buffer_does_not_allow_earlier_first_day_visits():
    start, end = date(2026, 10, 10), date(2026, 10, 11)
    window = resolve_travel_window(
        start, end, time(23, 30), time(17), "America/Toronto", 60
    )
    stops = schedule_draft(start, end, time(9), "America/Toronto", 3, ((0.0,),), window)
    assert len(stops) == 1 and stops[0].day == end
