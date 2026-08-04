# Product Requirements Document

## 1. Product summary

TripPilot is a constraint-aware travel-planning assistant for university
students planning affordable short trips around Canada and nearby US
destinations. The first MVP demonstrates that a user can provide practical
constraints and receive a feasible, transparent itinerary proposal based only
on mock data.

## 2. Problem

Short-trip planning requires reconciling dates, budget, travel time, opening
hours, personal interests, and energy level. General chat assistants can produce
appealing prose but may violate these constraints or invent availability.
TripPilot separates creative itinerary planning from deterministic validation.

## 3. Target user

A university student who:

- is planning an affordable leisure trip from a Canadian origin;
- has one destination city in Canada or a nearby US destination;
- has one to four calendar days available;
- wants a useful starting itinerary rather than a booking service; and
- values clear cost estimates and visible trade-offs.

## 4. MVP goals

- Collect the minimum inputs needed to plan a constrained short trip.
- Produce a readable day-by-day itinerary using versioned mock data.
- Deterministically identify violations of hard constraints.
- Clearly distinguish facts from estimates and proposals.
- Establish stable contracts for a later API, UI, database, and single
  coordinator agent.

## 5. Non-goals

The first MVP will not include:

- real bookings, reservation actions, or payments;
- authentication or user accounts;
- multi-city itineraries;
- live flight, hotel, map, weather, or venue APIs;
- visa, immigration, legal, or border-entry advice;
- retrieval-augmented generation (RAG) or MCP;
- multiple runtime agents or background workers;
- production deployment;
- guarantees of price, opening hours, availability, accessibility, or safety.

## 6. User inputs

All inputs cross a strict request boundary.

| Input | MVP rule |
| --- | --- |
| Origin | Required non-empty place label |
| Destination | Required single city; must differ from origin |
| Start and end dates | Required destination-local calendar dates; both are inclusive and the trip length must be 1–4 days |
| Travellers | Required integer, minimum 1; initial maximum 10 |
| Budget | Required positive all-in estimated total for all travellers, in integer minor units |
| Currency | Required supported ISO 4217 code; initially CAD or USD |
| Interests | At least one value from a documented set; optional free text is not accepted by the deterministic MVP endpoint |
| Pace | One of `relaxed`, `balanced`, or `packed` |
| Earliest activity time | Required local wall-clock time at the destination |

Initial interest values: `food`, `arts_culture`, `nature`, `history`,
`nightlife`, `shopping`, `sports`, and `student_budget`.

## 7. User experience

1. The user enters trip constraints in one form.
2. TripPilot validates the request and displays actionable field errors.
3. The planner selects transport, accommodation, activities, and meal estimates
   from mock provider records and proposes a day-by-day itinerary.
4. The deterministic validator checks the proposal.
5. A valid itinerary is presented with total and category cost estimates,
   assumptions, mock-data labels, and warnings. An invalid proposal is not shown
   as valid; violations are returned for correction or replanning.

## 8. Domain rules

### Hard constraints

- There is exactly one destination city.
- Start and end dates are inclusive destination-local calendar days, and the
  inclusive trip length is between one and four days.
- Arrival and departure transport times define the usable activity window on
  partial days. The inbound and outbound transport segments establish these
  boundaries and are not themselves required to fit within the usable activity
  window. Activities, meals, and local transfers cannot begin before arrival or
  end after departure.
- Every scheduled item, including inbound and outbound transport, falls within
  the trip-date envelope in the destination timezone. That envelope is the
  half-open interval from `start_date 00:00` through, but not including,
  `end_date + 1 day 00:00`.
- Time-blocking scheduled items do not overlap. Accommodation stays are modelled
  separately and do not participate in overlap validation.
- No activity begins before the user's earliest acceptable activity time.
- Scheduled activities, meals, and transport have strictly positive durations.
  A zero-duration event is valid only when explicitly modelled as a non-blocking
  marker, which does not participate in overlap validation.
- Each cost is non-negative.
- The all-in estimated total covers all travellers and includes transport to and
  from the destination, accommodation, activities, mock meal estimates, and
  explicit fees or taxes.
- Category totals are visible, sum exactly to the all-in itinerary total, and the
  all-in total does not exceed the stated budget.
- All monetary values in a validated itinerary use the request currency; mock
  conversion is out of scope.
- Traveller-count-dependent costs use the declared pricing basis consistently.
- Travel between consecutive locations has enough scheduled transfer time based
  on the mock data.
- Each selected record exists in the mock dataset and is available during its
  scheduled interval according to that dataset.
- Arrival and departure constraints cannot conflict with scheduled activities.

### Soft preferences

- Prefer activities matching stated interests.
- Match the approximate density of activities to travel pace.
- Prefer lower-cost options and leave a visible budget buffer when alternatives
  are otherwise comparable.
- Avoid excessive backtracking when mock location data permits comparison.

Soft preferences may influence ranking but never override a hard constraint.

## 9. Pace definition

Pace is a planning target, not a validity requirement:

- `relaxed`: typically 1–2 primary activities per full day.
- `balanced`: typically 2–3 primary activities per full day.
- `packed`: typically 3–4 primary activities per full day.

Meals, accommodation stays, and transfer segments are not counted as primary
activities.

## 10. Output requirements

The itinerary response contains:

- request summary and destination timezone;
- ordered days with time-blocking transport, meal, and activity items;
- accommodation stays listed separately from the time-blocking daily schedule;
- per-scheduled-item title, category, start/end time, location, estimated cost,
  and mock source identifier;
- an all-in estimated total for all travellers plus transport, accommodation,
  activity, meal, and fee/tax category totals in one currency;
- matched interests and planning rationale;
- assumptions and warnings;
- validation status and structured violations; and
- a prominent notice that all data is mock data and nothing has been booked.

## 11. MVP acceptance criteria

The MVP is accepted when all of the following are demonstrated locally:

1. A strict API request accepts all inputs in section 6 and rejects missing,
   malformed, or out-of-range values.
2. Only one destination and a one-to-four-day inclusive destination-local date
   range are accepted; arrival and departure transport constrain partial days.
3. At least three representative mock trips—one, two, and four days—can produce
   complete proposed itineraries without accessing a network.
4. The validator returns the same result for the same input and catches every
   hard rule listed in section 8 through dedicated unit tests.
5. The all-in cost for all travellers includes every required budget category,
   category totals reconcile exactly in integer minor units, and an over-budget
   itinerary is rejected.
6. No time-blocking scheduled item overlaps another; accommodation stays are
   excluded from overlap validation. No activity starts before the configured
   earliest activity time. No activity, meal, or local transfer occurs outside
   the arrival-to-departure usable window, violates relevant mock opening hours,
   or lacks transfer time. Boundary transport is checked against the inclusive
   trip-date envelope rather than the usable window it defines.
7. Activities, meals, and transport have strictly positive durations, and only
   explicitly non-blocking markers may have zero duration.
8. Every scheduled item and accommodation stay references a valid mock-data
   record where applicable.
9. Responses clearly label mock data and estimates and state that no booking was
   made.
10. Provider implementations can be substituted through interfaces without
   changing domain validation logic.
11. The complete pytest suite passes offline and requires no secrets.

## 12. Success indicators

For a fixed evaluation set:

- 100% hard-constraint compliance on responses marked valid;
- 100% arithmetic agreement between itemized and reported costs;
- 100% presence of the mock-data/no-booking disclosure;
- at least 90% of generated plans satisfy the pace and interest heuristics; and
- median local planning latency is recorded as a baseline, not an MVP gate.

## 13. Later roadmap

The deterministic core, FastAPI endpoint, and Next.js client are complete. The
next bounded experiment is one optional coordinator that ranks two to five
deterministically generated, validator-clean candidates using soft preferences.
It does not generate authoritative itinerary facts and is retained only if the
gates in `docs/COORDINATOR_EXPERIMENT.md` pass. Persistence, selected live
providers, containerization, and deployment remain later changes requiring
separate scope and threat reviews.

The approved experiment may add `preference_notes`: optional soft-preference
text normalized and limited to at most 300 Unicode code points. It is not part
of the accepted deterministic endpoint. When implemented behind explicit
experiment opt-in, it is treated as untrusted ranking input and cannot override
structured constraints
or add supported requirements. Booking, payment, multi-city, visa, safety,
medical, dietary, mobility, accessibility, and current-availability requests in
this field must not be presented as satisfied.

## 14. Open product decisions

- Exact supported origin/destination list and contents of the initial fixture set.
- Whether the traveller maximum of 10 is suitable for the intended UX.
- Accessibility, dietary, and mobility constraints for the next MVP iteration.
