from datetime import date, time

import pytest

from trippilot.domain.live_draft import schedule_draft


def make_schedule(
    *, days=2, start=time(9), matrix=None, target=3, zone="America/Toronto"
):
    return schedule_draft(
        date(2026, 10, 10),
        date(2026, 10, 9 + days),
        start,
        zone,
        target,
        matrix or tuple(tuple(61.0 for _ in range(8)) for _ in range(8)),
    )


def test_no_repeats_inclusive_days_and_local_time():
    stops = make_schedule(days=4)
    assert len(stops) == 8
    assert len({s.place_index for s in stops}) == 8
    assert {s.day for s in stops} == {date(2026, 10, d) for d in range(10, 14)}
    assert all(
        s.start.hour >= 9 and s.end.hour <= 18 and s.end > s.start for s in stops
    )
    assert all(s.start.utcoffset().total_seconds() == -14400 for s in stops)


def test_walk_time_rounds_up_and_reserves_break():
    stops = make_schedule(days=1)
    assert stops[1].walk_minutes == 2
    assert (stops[1].start - stops[0].end).total_seconds() == 32 * 60


def test_unknown_or_long_route_never_invented():
    for seconds in (None, 2701.0):
        stops = make_schedule(days=1, matrix=((0.0, seconds), (seconds, 0.0)))
        assert len(stops) == 1


def test_zero_route_uses_positive_transfer_allowance():
    stops = make_schedule(days=1, matrix=((0.0, 0.0), (0.0, 0.0)))
    assert stops[1].walk_minutes == 1


def test_late_start_cannot_extend_beyond_day():
    assert make_schedule(start=time(18)) == ()
    assert all(s.start.hour >= 16 for s in make_schedule(start=time(16)))


@pytest.mark.parametrize("days", [0, 5])
def test_bad_trip_length(days):
    with pytest.raises(ValueError):
        make_schedule(days=days)


def test_invalid_matrix_and_candidate_caps():
    with pytest.raises(ValueError):
        make_schedule(matrix=((1.0, 2.0),))
    with pytest.raises(ValueError):
        make_schedule(matrix=tuple((1.0,) * 9 for _ in range(9)))


def test_dst_uses_destination_local_days():
    stops = schedule_draft(
        date(2026, 10, 31),
        date(2026, 11, 1),
        time(9),
        "America/Toronto",
        1,
        ((0.0, 60.0), (60.0, 0.0)),
    )
    assert [s.start.hour for s in stops] == [9, 9]
    assert [s.start.utcoffset().total_seconds() for s in stops] == [-14400, -18000]
