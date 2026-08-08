"""Small, bounded, deterministic itinerary-planning baseline."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from heapq import heappop, heappush
from itertools import permutations
from typing import cast
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from trippilot.domain import (
    AccommodationStay,
    CostBreakdown,
    ExplicitFee,
    Interest,
    ItemKind,
    Itinerary,
    Money,
    OperatingWindow,
    Pace,
    Pricing,
    PricingBasis,
    ProviderSnapshot,
    ScheduledItem,
    TimeWindow,
    TransferRequirement,
    TransportRole,
    TripRequest,
    ValidationReport,
    validate_itinerary,
)
from trippilot.domain.schemas import CurrencyCode, MoneySchema, TripRequestSchema
from trippilot.providers import (
    AccommodationOptionRecord,
    ActivityRecord,
    MealOptionRecord,
    PriceRecord,
    TransportOptionRecord,
    TravelDataProvider,
)

from .models import (
    CandidateEnumerationResult,
    CandidateSet,
    CanonicalCandidate,
    PlanningFailure,
    PlanningFailureCode,
    PlanningResult,
    PlanningSuccess,
)

PLANNER_ID = "deterministic-greedy-bounded-v1"
CANDIDATE_GENERATOR_ID = "deterministic-candidate-enumerator-v1"
MAX_CANONICAL_CANDIDATES = 5
MAX_CANDIDATE_COMBINATIONS = 32
MAX_AGENDA_VARIANTS_PER_DAY = 5_000

ASSUMPTIONS = (
    "One mock meal estimate is included for each usable destination day.",
    "Transfer gaps use the shortest directed path in the supplied estimates.",
    "Pace is a soft target and may be reduced when time or budget requires it.",
)
DISCLOSURES = (
    "All prices, schedules, operating hours, and availability are mock estimates.",
    "Nothing has been booked or reserved; verify all details before purchase.",
)

type SelectableRecord = ActivityRecord | MealOptionRecord
type LocatedProviderRecord = (
    AccommodationOptionRecord | ActivityRecord | MealOptionRecord
)
type CandidateCombination = tuple[
    int,
    int,
    str,
    str,
    str,
    TransportOptionRecord,
    TransportOptionRecord,
    AccommodationOptionRecord | None,
]


@dataclass(frozen=True, slots=True)
class _Graph:
    edges: dict[str, tuple[tuple[str, int], ...]]

    def shortest_minutes(self, start: str, end: str) -> int | None:
        if start == end:
            return 0
        queue: list[tuple[int, str]] = [(0, start)]
        best = {start: 0}
        while queue:
            minutes, location = heappop(queue)
            if location == end:
                return minutes
            if minutes != best[location]:
                continue
            for next_location, edge_minutes in self.edges.get(location, ()):
                candidate = minutes + edge_minutes
                if candidate < best.get(next_location, candidate + 1):
                    best[next_location] = candidate
                    heappush(queue, (candidate, next_location))
        return None


@dataclass(frozen=True, slots=True)
class _Agenda:
    items: tuple[ScheduledItem, ...]
    activity_count: int
    interest_matches: int
    cost_minor: int
    transfer_minutes: int
    record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    itinerary: Itinerary
    snapshot: ProviderSnapshot
    matched_interests: tuple[Interest, ...]
    interest_counts: tuple[int, ...]
    daypart_counts: tuple[int, int, int]


def _activity_signature(candidate: _Candidate) -> tuple[str, ...]:
    return tuple(
        item.source_record_id or ""
        for item in candidate.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )


def _tradeoff_signature(
    candidate: _Candidate,
) -> tuple[int, int, int, tuple[int, ...], tuple[int, int, int]]:
    return (
        candidate.itinerary.total_estimated_cost.amount_minor,
        sum(
            requirement.minimum_minutes
            for requirement in candidate.snapshot.transfer_requirements
        ),
        len(_activity_signature(candidate)),
        candidate.interest_counts,
        candidate.daypart_counts,
    )


def _is_materially_different(
    candidate: _Candidate,
    existing: _Candidate,
    *,
    budget_minor: int,
) -> bool:
    candidate_activities = _activity_signature(candidate)
    existing_activities = _activity_signature(existing)
    if candidate_activities == existing_activities:
        return False

    candidate_tradeoffs = _tradeoff_signature(candidate)
    existing_tradeoffs = _tradeoff_signature(existing)
    cost_threshold = min(500, (budget_minor * 5 + 99) // 100)
    return (
        abs(candidate_tradeoffs[0] - existing_tradeoffs[0]) >= cost_threshold
        or abs(candidate_tradeoffs[1] - existing_tradeoffs[1]) >= 15
        or candidate_tradeoffs[2] != existing_tradeoffs[2]
        or candidate_tradeoffs[3] != existing_tradeoffs[3]
        or candidate_tradeoffs[4] != existing_tradeoffs[4]
    )


def _failure(
    code: PlanningFailureCode,
    explanation: str,
    constraints: tuple[str, ...],
    snapshot_version: str | None,
    report: ValidationReport | None = None,
) -> PlanningFailure:
    return PlanningFailure(
        code=code,
        explanation=explanation,
        validation_report=report or ValidationReport(()),
        relevant_constraints=constraints,
        fixture_snapshot_version=snapshot_version,
        planner_id=PLANNER_ID,
        assumptions=ASSUMPTIONS,
        disclosures=DISCLOSURES,
    )


def _request_is_valid(request: TripRequest) -> bool:
    try:
        TripRequestSchema(
            origin=request.origin,
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            travellers=request.travellers,
            budget=MoneySchema(
                amount_minor=request.budget.amount_minor,
                currency=cast(CurrencyCode, request.budget.currency),
            ),
            interests=request.interests,
            pace=request.pace,
            earliest_activity_time=request.earliest_activity_time,
            destination_timezone=request.destination_timezone,
        )
    except ValidationError, TypeError, ValueError:
        return False
    return True


def _normalized_amount(price: PriceRecord, travellers: int, units: int = 1) -> int:
    multiplier = travellers if price.basis is PricingBasis.PER_PERSON else 1
    return price.amount_minor * multiplier * units


def _pricing(price: PriceRecord, travellers: int, units: int = 1) -> Pricing:
    per_charge = price.amount_minor * units
    charged = travellers if price.basis is PricingBasis.PER_PERSON else None
    return Pricing(
        basis=price.basis,
        unit_price=Money(per_charge, price.currency.value),
        charged_travellers=charged,
    )


def _record_cost_with_fees(
    provider: TravelDataProvider,
    record_id: str,
    price: PriceRecord,
    travellers: int,
    units: int = 1,
) -> int:
    amount = _normalized_amount(price, travellers, units)
    return amount + sum(
        _normalized_amount(fee.price, travellers)
        for fee in provider.list_fees(record_id)
    )


def _inside_envelope(value: datetime, start: datetime, end: datetime) -> bool:
    instant = value.astimezone(UTC)
    return start.astimezone(UTC) <= instant <= end.astimezone(UTC)


def _transport_item(
    record: TransportOptionRecord,
    role: TransportRole,
    travellers: int,
) -> ScheduledItem:
    amount = _normalized_amount(record.price, travellers)
    location_id = (
        record.destination_location_id
        if role is TransportRole.INBOUND
        else record.origin_location_id
    )
    return ScheduledItem(
        item_id=f"{role.value}-{record.record_id}",
        title=record.title,
        kind=ItemKind.TRANSPORT,
        window=TimeWindow(record.departure_at, record.arrival_at),
        location_id=location_id,
        estimated_cost=Money(amount, record.currency.value),
        source_record_id=record.record_id,
        pricing=_pricing(record.price, travellers),
        transport_role=role,
    )


def _operating_windows(
    provider: TravelDataProvider, record: SelectableRecord, day: date, zone: ZoneInfo
) -> tuple[tuple[datetime, datetime], ...]:
    windows: list[tuple[datetime, datetime]] = []
    for window in provider.get_operating_windows(record.record_id):
        if day.weekday() in window.weekdays:
            windows.append(
                (
                    datetime.combine(day, window.local_start_time, zone),
                    datetime.combine(day, window.local_end_time, zone),
                )
            )
    return tuple(sorted(windows))


def _scheduled_record(
    record: SelectableRecord,
    start: datetime,
    travellers: int,
    sequence: int,
) -> ScheduledItem:
    kind = ItemKind.ACTIVITY if isinstance(record, ActivityRecord) else ItemKind.MEAL
    amount = _normalized_amount(record.price, travellers)
    return ScheduledItem(
        item_id=f"{start.date().isoformat()}-{sequence:02d}-{record.record_id}",
        title=record.title,
        kind=kind,
        window=TimeWindow(start, start + timedelta(minutes=record.duration_minutes)),
        location_id=record.location_id,
        estimated_cost=Money(amount, record.currency.value),
        source_record_id=record.record_id,
        pricing=_pricing(record.price, travellers),
    )


def _schedule_sequence(
    records: Sequence[SelectableRecord],
    *,
    day: date,
    day_start: datetime,
    day_end: datetime,
    start_location: str,
    end_location: str,
    request: TripRequest,
    provider: TravelDataProvider,
    graph: _Graph,
    zone: ZoneInfo,
) -> _Agenda | None:
    cursor = day_start
    location = start_location
    scheduled: list[ScheduledItem] = []
    transfer_total = 0
    for sequence, record in enumerate(records, start=1):
        transfer = graph.shortest_minutes(location, record.location_id)
        if transfer is None:
            return None
        ready = cursor + timedelta(minutes=transfer)
        if isinstance(record, ActivityRecord):
            earliest = datetime.combine(day, request.earliest_activity_time, zone)
            ready = max(ready, earliest)
        start = None
        for window_start, window_end in _operating_windows(provider, record, day, zone):
            candidate = max(ready, window_start)
            end = candidate + timedelta(minutes=record.duration_minutes)
            if end <= window_end and end <= day_end:
                start = candidate
                break
        if start is None:
            return None
        item = _scheduled_record(record, start, request.travellers, sequence)
        scheduled.append(item)
        cursor = item.window.end
        location = record.location_id
        transfer_total += transfer

    final_transfer = graph.shortest_minutes(location, end_location)
    if final_transfer is None or cursor + timedelta(minutes=final_transfer) > day_end:
        return None
    transfer_total += final_transfer
    activities = tuple(
        record for record in records if isinstance(record, ActivityRecord)
    )
    requested = set(request.interests)
    return _Agenda(
        items=tuple(scheduled),
        activity_count=len(activities),
        interest_matches=sum(
            len(requested.intersection(record.interests)) for record in activities
        ),
        cost_minor=sum(
            _record_cost_with_fees(
                provider, record.record_id, record.price, request.travellers
            )
            for record in records
        ),
        transfer_minutes=transfer_total,
        record_ids=tuple(record.record_id for record in records),
    )


def _best_agenda(
    activities: tuple[ActivityRecord, ...],
    meals: tuple[MealOptionRecord, ...],
    *,
    target: int,
    day: date,
    day_start: datetime,
    day_end: datetime,
    start_location: str,
    end_location: str,
    request: TripRequest,
    provider: TravelDataProvider,
    graph: _Graph,
    cost_first: bool,
    zone: ZoneInfo,
) -> _Agenda | None:
    requested = set(request.interests)
    ordered_activities = tuple(
        sorted(
            activities,
            key=lambda record: (
                -len(requested.intersection(record.interests)),
                _normalized_amount(record.price, request.travellers),
                record.record_id,
            ),
        )
    )
    ordered_meals = tuple(
        sorted(
            meals,
            key=lambda record: (
                _normalized_amount(record.price, request.travellers),
                record.record_id,
            ),
        )
    )
    variants = 0
    feasible: list[_Agenda] = []
    for count in range(min(target, len(ordered_activities)), -1, -1):
        for activity_order in permutations(ordered_activities, count):
            for meal in ordered_meals:
                for meal_index in range(count + 1):
                    variants += 1
                    if variants > MAX_AGENDA_VARIANTS_PER_DAY:
                        break
                    sequence: list[SelectableRecord] = list(activity_order)
                    sequence.insert(meal_index, meal)
                    agenda = _schedule_sequence(
                        sequence,
                        day=day,
                        day_start=day_start,
                        day_end=day_end,
                        start_location=start_location,
                        end_location=end_location,
                        request=request,
                        provider=provider,
                        graph=graph,
                        zone=zone,
                    )
                    if agenda is not None:
                        feasible.append(agenda)
                if variants > MAX_AGENDA_VARIANTS_PER_DAY:
                    break
            if variants > MAX_AGENDA_VARIANTS_PER_DAY:
                break
        if feasible or variants > MAX_AGENDA_VARIANTS_PER_DAY:
            break
    if not feasible:
        return None

    def rank(agenda: _Agenda) -> tuple[object, ...]:
        preference = (
            (agenda.cost_minor, -agenda.interest_matches)
            if cost_first
            else (-agenda.interest_matches, agenda.cost_minor)
        )
        return (
            -agenda.activity_count,
            *preference,
            agenda.transfer_minutes,
            agenda.record_ids,
            tuple(item.window.start for item in agenda.items),
        )

    return min(feasible, key=rank)


def _graph_for(
    provider: TravelDataProvider,
    records: Iterable[LocatedProviderRecord],
    transport: tuple[TransportOptionRecord, TransportOptionRecord],
) -> _Graph:
    locations = {record.location_id for record in records}
    locations.update(
        {
            transport[0].destination_location_id,
            transport[1].origin_location_id,
        }
    )
    edges: dict[str, list[tuple[str, int]]] = {}
    for start in sorted(locations):
        for end in sorted(locations):
            estimate = provider.get_transfer_estimate(start, end)
            if estimate is not None:
                edges.setdefault(start, []).append((end, estimate.duration_minutes))
    return _Graph({key: tuple(sorted(value)) for key, value in edges.items()})


def _fees_for(
    provider: TravelDataProvider,
    selected_record_ids: Iterable[str],
    travellers: int,
    currency: str,
) -> tuple[ExplicitFee, ...]:
    fees: list[ExplicitFee] = []
    for sequence, record_id in enumerate(selected_record_ids, start=1):
        for fee in sorted(
            provider.list_fees(record_id), key=lambda record: record.record_id
        ):
            amount = _normalized_amount(fee.price, travellers)
            fees.append(
                ExplicitFee(
                    fee_id=f"fee-{sequence:03d}-{fee.record_id}",
                    title=fee.title,
                    cost=Money(amount, currency),
                )
            )
    return tuple(fees)


def _provider_snapshot(
    provider: TravelDataProvider,
    itinerary: Itinerary,
    request: TripRequest,
    graph: _Graph,
) -> ProviderSnapshot:
    record_ids = frozenset(
        source_id
        for source_id in (
            *(item.source_record_id for item in itinerary.scheduled_items),
            *(stay.source_record_id for stay in itinerary.accommodation_stays),
        )
        if source_id is not None and provider.get_record(source_id) is not None
    )
    zone = ZoneInfo(request.destination_timezone)
    operating: list[OperatingWindow] = []
    for item in itinerary.scheduled_items:
        if item.kind not in {ItemKind.ACTIVITY, ItemKind.MEAL} or (
            item.source_record_id is None
        ):
            continue
        for window in sorted(
            provider.get_operating_windows(item.source_record_id),
            key=lambda record: (
                record.local_start_time,
                record.local_end_time,
                record.weekdays,
                record.record_id,
            ),
        ):
            local_day = item.window.start.astimezone(zone).date()
            if local_day.weekday() in window.weekdays:
                operating.append(
                    OperatingWindow(
                        item.source_record_id,
                        TimeWindow(
                            datetime.combine(local_day, window.local_start_time, zone),
                            datetime.combine(local_day, window.local_end_time, zone),
                        ),
                    )
                )
    chronological = sorted(
        itinerary.scheduled_items,
        key=lambda item: (item.window.start.astimezone(UTC), item.item_id),
    )
    transfers: list[TransferRequirement] = []
    for first, second in zip(chronological, chronological[1:], strict=False):
        if first.location_id is None or second.location_id is None:
            continue
        minutes = graph.shortest_minutes(first.location_id, second.location_id)
        if minutes is not None and first.location_id != second.location_id:
            transfers.append(
                TransferRequirement(first.location_id, second.location_id, minutes)
            )
    return ProviderSnapshot(record_ids, tuple(operating), tuple(transfers))


def _candidate(
    request: TripRequest,
    provider: TravelDataProvider,
    inbound: TransportOptionRecord,
    outbound: TransportOptionRecord,
    accommodation: AccommodationOptionRecord | None,
    activities: tuple[ActivityRecord, ...],
    meals: tuple[MealOptionRecord, ...],
    daily_activity_targets: tuple[int, ...],
    *,
    cost_first: bool,
) -> _Candidate | None:
    zone = ZoneInfo(request.destination_timezone)
    transfer_waypoints = (
        provider.list_accommodation_options(activities[0].destination_id)
        if activities
        else ()
    )
    records: tuple[LocatedProviderRecord, ...] = (
        *activities,
        *meals,
        *transfer_waypoints,
        *((accommodation,) if accommodation is not None else ()),
    )
    graph = _graph_for(provider, records, (inbound, outbound))
    scheduled: list[ScheduledItem] = [
        _transport_item(inbound, TransportRole.INBOUND, request.travellers)
    ]
    selected_ids: list[str] = [inbound.record_id, outbound.record_id]
    trip_days = (request.end_date - request.start_date).days + 1
    if len(daily_activity_targets) != trip_days:
        return None
    activity_interests: set[Interest] = set()
    activity_interest_counts = {interest: 0 for interest in Interest}
    for offset in range(trip_days):
        day = request.start_date + timedelta(days=offset)
        first_day = offset == 0
        last_day = offset == trip_days - 1
        if first_day:
            day_start = inbound.arrival_at.astimezone(zone)
            start_location = inbound.destination_location_id
        else:
            day_start = datetime.combine(day, time(8), zone)
            if accommodation is None:
                return None
            start_location = accommodation.location_id
        if last_day:
            day_end = outbound.departure_at.astimezone(zone)
            end_location = outbound.origin_location_id
        else:
            day_end = datetime.combine(day, time(22), zone)
            if accommodation is None:
                return None
            end_location = accommodation.location_id
        if day_start >= day_end:
            return None
        agenda = _best_agenda(
            activities,
            meals,
            target=daily_activity_targets[offset],
            day=day,
            day_start=day_start,
            day_end=day_end,
            start_location=start_location,
            end_location=end_location,
            request=request,
            provider=provider,
            graph=graph,
            cost_first=cost_first,
            zone=zone,
        )
        if agenda is None:
            return None
        scheduled.extend(agenda.items)
        selected_ids.extend(agenda.record_ids)
        for record_id in agenda.record_ids:
            record = provider.get_record(record_id)
            if isinstance(record, ActivityRecord):
                activity_interests.update(record.interests)
                for interest in record.interests:
                    activity_interest_counts[interest] += 1
    scheduled.append(
        _transport_item(outbound, TransportRole.OUTBOUND, request.travellers)
    )

    stays: tuple[AccommodationStay, ...] = ()
    if accommodation is not None:
        nights = (request.end_date - request.start_date).days
        amount = _normalized_amount(
            accommodation.nightly_price, request.travellers, nights
        )
        stays = (
            AccommodationStay(
                stay_id=f"stay-{accommodation.record_id}",
                title=accommodation.title,
                check_in=datetime.combine(
                    request.start_date, accommodation.check_in_time, zone
                ),
                check_out=datetime.combine(
                    request.end_date, accommodation.check_out_time, zone
                ),
                number_of_nights=nights,
                location_id=accommodation.location_id,
                estimated_cost=Money(amount, request.budget.currency),
                source_record_id=accommodation.record_id,
                pricing=_pricing(
                    accommodation.nightly_price, request.travellers, nights
                ),
            ),
        )
        selected_ids.append(accommodation.record_id)

    scheduled_tuple = tuple(
        sorted(
            scheduled,
            key=lambda item: (item.window.start.astimezone(UTC), item.item_id),
        )
    )
    fees = _fees_for(
        provider, selected_ids, request.travellers, request.budget.currency
    )
    amounts = {
        "transport": sum(
            item.estimated_cost.amount_minor
            for item in scheduled_tuple
            if item.kind is ItemKind.TRANSPORT
        ),
        "accommodation": sum(stay.estimated_cost.amount_minor for stay in stays),
        "activity": sum(
            item.estimated_cost.amount_minor
            for item in scheduled_tuple
            if item.kind is ItemKind.ACTIVITY
        ),
        "meal": sum(
            item.estimated_cost.amount_minor
            for item in scheduled_tuple
            if item.kind is ItemKind.MEAL
        ),
        "fees_taxes": sum(fee.cost.amount_minor for fee in fees),
    }
    currency = request.budget.currency
    itinerary = Itinerary(
        scheduled_items=scheduled_tuple,
        accommodation_stays=stays,
        explicit_fees=fees,
        category_totals=CostBreakdown(
            transport=Money(amounts["transport"], currency),
            accommodation=Money(amounts["accommodation"], currency),
            activity=Money(amounts["activity"], currency),
            meal=Money(amounts["meal"], currency),
            fees_taxes=Money(amounts["fees_taxes"], currency),
        ),
        total_estimated_cost=Money(sum(amounts.values()), currency),
    )
    snapshot = _provider_snapshot(provider, itinerary, request, graph)
    daypart_counts = [0, 0, 0]
    for item in scheduled_tuple:
        if item.kind is not ItemKind.ACTIVITY:
            continue
        hour = item.window.start.astimezone(zone).hour
        daypart_counts[0 if hour < 12 else 1 if hour < 18 else 2] += 1
    return _Candidate(
        itinerary=itinerary,
        snapshot=snapshot,
        matched_interests=tuple(
            interest for interest in request.interests if interest in activity_interests
        ),
        interest_counts=tuple(
            activity_interest_counts[interest] for interest in Interest
        ),
        daypart_counts=(
            daypart_counts[0],
            daypart_counts[1],
            daypart_counts[2],
        ),
    )


def _pace_target(pace: Pace) -> int:
    return {Pace.RELAXED: 1, Pace.BALANCED: 2, Pace.PACKED: 3}[pace]


def _daily_target_profiles(request: TripRequest) -> tuple[tuple[int, ...], ...]:
    days = (request.end_date - request.start_date).days + 1
    pace_target = _pace_target(request.pace)
    profiles = [tuple([target] * days) for target in range(pace_target, 0, -1)]
    profiles.extend(
        tuple(1 if offset == activity_day else 0 for offset in range(days))
        for activity_day in range(days)
    )
    return tuple(dict.fromkeys(profiles))


def _enumerate_trip_candidates(
    request: TripRequest,
    provider: TravelDataProvider,
    *,
    max_candidates: int,
) -> CandidateEnumerationResult:
    """Search the current bounded traversal for ordered canonical proposals."""

    if not _request_is_valid(request):
        return _failure(
            PlanningFailureCode.INVALID_REQUEST,
            "The trip request does not satisfy the normalized request boundary.",
            ("valid normalized TripRequest", "one-to-four inclusive days"),
            None,
        )
    try:
        metadata = provider.get_snapshot_metadata()
        snapshot_version = metadata.snapshot_version
        destination = provider.get_destination(request.destination)
        if destination is None:
            return _failure(
                PlanningFailureCode.UNSUPPORTED_ROUTE,
                "The provider snapshot does not support the requested destination.",
                (request.destination,),
                snapshot_version,
            )
        if (
            destination.timezone != request.destination_timezone
            or request.budget.currency
            not in {value.value for value in metadata.supported_currencies}
        ):
            return _failure(
                PlanningFailureCode.PROVIDER_DATA_INCOMPLETE,
                "Provider timezone or currency metadata is incompatible with "
                "the request.",
                (request.destination_timezone, request.budget.currency),
                snapshot_version,
            )
        zone = ZoneInfo(request.destination_timezone)
        envelope_start = datetime.combine(request.start_date, time.min, zone)
        envelope_end = datetime.combine(
            request.end_date + timedelta(days=1), time.min, zone
        )
        inbound = tuple(
            record
            for record in provider.list_transport_options(
                request.origin, request.destination
            )
            if record.currency.value == request.budget.currency
            and record.arrival_at.astimezone(zone).date() == request.start_date
            and _inside_envelope(record.departure_at, envelope_start, envelope_end)
            and _inside_envelope(record.arrival_at, envelope_start, envelope_end)
        )
        outbound = tuple(
            record
            for record in provider.list_transport_options(
                request.destination, request.origin
            )
            if record.currency.value == request.budget.currency
            and record.departure_at.astimezone(zone).date() == request.end_date
            and _inside_envelope(record.departure_at, envelope_start, envelope_end)
            and _inside_envelope(record.arrival_at, envelope_start, envelope_end)
        )
        if not inbound or not outbound:
            return _failure(
                PlanningFailureCode.NO_TRANSPORT_OPTION,
                "No complete outbound-and-return transport pair fits the trip dates.",
                (
                    request.origin,
                    request.destination,
                    str(request.start_date),
                    str(request.end_date),
                ),
                snapshot_version,
            )
        nights = (request.end_date - request.start_date).days
        accommodations: tuple[AccommodationOptionRecord | None, ...]
        if nights:
            available_stays = tuple(
                record
                for record in provider.list_accommodation_options(destination.record_id)
                if record.currency.value == request.budget.currency
                and record.minimum_nights <= nights <= record.maximum_nights
            )
            if not available_stays:
                return _failure(
                    PlanningFailureCode.NO_ACCOMMODATION_OPTION,
                    "No accommodation option supports the required number of nights.",
                    (f"{nights} overnight stay(s)",),
                    snapshot_version,
                )
            accommodations = available_stays
        else:
            accommodations = (None,)
        activities = tuple(
            record
            for record in provider.list_activities(destination.record_id)
            if record.currency.value == request.budget.currency
        )
        meals = tuple(
            record
            for record in provider.list_meal_options(destination.record_id)
            if record.currency.value == request.budget.currency
        )
        if not activities or not meals:
            return _failure(
                PlanningFailureCode.PROVIDER_DATA_INCOMPLETE,
                "The snapshot lacks activity or meal records required for a "
                "complete plan.",
                ("at least one activity", "one meal option per usable day"),
                snapshot_version,
            )

        combinations: list[CandidateCombination] = []
        for inbound_record in inbound:
            for outbound_record in outbound:
                if inbound_record.arrival_at.astimezone(
                    UTC
                ) > outbound_record.departure_at.astimezone(UTC):
                    continue
                for stay in accommodations:
                    fixed_cost = _record_cost_with_fees(
                        provider,
                        inbound_record.record_id,
                        inbound_record.price,
                        request.travellers,
                    )
                    fixed_cost += _record_cost_with_fees(
                        provider,
                        outbound_record.record_id,
                        outbound_record.price,
                        request.travellers,
                    )
                    if stay is not None:
                        fixed_cost += _record_cost_with_fees(
                            provider,
                            stay.record_id,
                            stay.nightly_price,
                            request.travellers,
                            nights,
                        )
                    duration = int(
                        (
                            inbound_record.arrival_at - inbound_record.departure_at
                        ).total_seconds()
                        + (
                            outbound_record.arrival_at - outbound_record.departure_at
                        ).total_seconds()
                    )
                    combinations.append(
                        (
                            fixed_cost,
                            duration,
                            inbound_record.record_id,
                            outbound_record.record_id,
                            stay.record_id if stay else "",
                            inbound_record,
                            outbound_record,
                            stay,
                        )
                    )
        combinations.sort(key=lambda value: value[:5])
        if not combinations:
            return _failure(
                PlanningFailureCode.NO_TRANSPORT_OPTION,
                "Transport options exist but no chronological pair is feasible.",
                ("arrival before departure",),
                snapshot_version,
            )

        last_report: ValidationReport | None = None
        saw_activity_candidate = False
        saw_within_budget = False
        accepted: list[tuple[_Candidate, ValidationReport]] = []
        for combination in combinations[:MAX_CANDIDATE_COMBINATIONS]:
            _, _, _, _, _, inbound_record, outbound_record, stay = combination
            for targets in _daily_target_profiles(request):
                for cost_first in (False, True):
                    candidate = _candidate(
                        request,
                        provider,
                        inbound_record,
                        outbound_record,
                        stay,
                        activities,
                        meals,
                        targets,
                        cost_first=cost_first,
                    )
                    if candidate is None:
                        continue
                    if not any(
                        item.kind is ItemKind.ACTIVITY
                        for item in candidate.itinerary.scheduled_items
                    ):
                        continue
                    saw_activity_candidate = True
                    report = validate_itinerary(
                        request, candidate.itinerary, candidate.snapshot
                    )
                    last_report = report
                    if (
                        candidate.itinerary.total_estimated_cost.amount_minor
                        > request.budget.amount_minor
                    ):
                        continue
                    saw_within_budget = True
                    if report.is_valid:
                        if accepted and not all(
                            _is_materially_different(
                                candidate,
                                existing_candidate,
                                budget_minor=request.budget.amount_minor,
                            )
                            for existing_candidate, _ in accepted
                        ):
                            continue
                        accepted.append((candidate, report))
                        if len(accepted) == max_candidates:
                            return _candidate_set(accepted, snapshot_version)
        if accepted:
            return _candidate_set(accepted, snapshot_version)
        if saw_activity_candidate and not saw_within_budget:
            return _failure(
                PlanningFailureCode.INSUFFICIENT_BUDGET,
                "Every complete schedulable proposal exceeds the all-in budget.",
                (f"budget {request.budget.amount_minor} {request.budget.currency}",),
                snapshot_version,
                last_report,
            )
        if not saw_activity_candidate:
            return _failure(
                PlanningFailureCode.NO_FEASIBLE_ACTIVITY_SET,
                "No activity-and-meal agenda fits the time, hours, and transfer "
                "constraints.",
                ("operating windows", "earliest activity time", "transfer estimates"),
                snapshot_version,
                last_report,
            )
        return _failure(
            PlanningFailureCode.NO_VALID_ITINERARY,
            "Bounded candidate search found proposals, but none passed complete "
            "validation.",
            (f"{MAX_CANDIDATE_COMBINATIONS} candidate combinations",),
            snapshot_version,
            last_report,
        )
    except Exception as error:  # Provider implementations are an external boundary.
        return _failure(
            PlanningFailureCode.PROVIDER_DATA_INCOMPLETE,
            f"Provider data could not be used safely: {type(error).__name__}.",
            ("strict provider contract", "complete referenced records"),
            locals().get("snapshot_version"),
        )


def _candidate_set(
    candidates: list[tuple[_Candidate, ValidationReport]], snapshot_version: str
) -> CandidateSet:
    return CandidateSet(
        candidates=tuple(
            CanonicalCandidate(
                itinerary=candidate.itinerary,
                provider_snapshot=candidate.snapshot,
                validation_report=report,
                matched_interests=candidate.matched_interests,
            )
            for candidate, report in candidates
        ),
        fixture_snapshot_version=snapshot_version,
        generator_id=CANDIDATE_GENERATOR_ID,
        assumptions=ASSUMPTIONS,
        disclosures=DISCLOSURES,
    )


def _validated_candidate_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= 5:
        raise ValueError("candidate limit must be an integer between two and five")
    return value


def enumerate_trip_candidates(
    request: TripRequest,
    provider: TravelDataProvider,
    *,
    limit: int = MAX_CANONICAL_CANDIDATES,
) -> CandidateEnumerationResult:
    """Return one to five distinct canonical candidates, or a planning failure.

    Fewer than two candidates is a valid result and tells the future coordinator
    to skip model selection rather than pad the set with cosmetic duplicates.
    """

    return _enumerate_trip_candidates(
        request, provider, max_candidates=_validated_candidate_limit(limit)
    )


def plan_trip(request: TripRequest, provider: TravelDataProvider) -> PlanningResult:
    """Return the existing first validator-clean proposal or structured failure."""

    result = _enumerate_trip_candidates(request, provider, max_candidates=1)
    if isinstance(result, PlanningFailure):
        return result
    candidate = result.candidates[0]
    return PlanningSuccess(
        itinerary=candidate.itinerary,
        validation_report=candidate.validation_report,
        fixture_snapshot_version=result.fixture_snapshot_version,
        planner_id=PLANNER_ID,
        matched_interests=candidate.matched_interests,
        assumptions=result.assumptions,
        disclosures=result.disclosures,
    )
