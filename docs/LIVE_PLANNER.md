# Live main planner — places, travel windows and entered costs

Approved by the user on September 26, 2026: replace fixture-only main planning
with external places/routes, starting with a free Geoapify account. This changes
the main experience, not just the existing `/research` feature.

## What works and what does not

The homepage now creates a live **draft** for one Canada/US destination and
one to four inclusive local dates. It resolves the city and IANA timezone,
searches named places within 5 km of the city centre, and retrieves walking
times. Multiple city matches require a more specific destination; they are not
silently resolved by choosing the first result. No fixture date range applies.

Up to three interest categories are searched in selected order. At most eight
unique candidates are interleaved across categories. A bounded nearest-next
scheduler distributes those candidates across the requested days with pace
targets of two/three/four stops. Visits are explicitly estimated at 60 minutes;
30-minute breaks and rounded-up walking times are reserved. No walking leg over
45 minutes or missing route is guessed. Some days may remain empty or sparse.
`student_budget` searches sightseeing, **not verified free admission**. Nightlife
and all other categories currently use the same provisional daytime envelope;
venue opening hours are not interpreted or validated.

This is not yet a complete live trip planner. Without entered travel times it
assumes the traveller is in the city for the provisional 09:00–18:00 day (or
later requested start). Optional travel times constrain that envelope, as
described below. There are still no verified intercity fares, lodging prices or
availability, meal/activity costs, fees/taxes, or date-specific opening hours.
No unknown price is filled with zero, no full validity flag is emitted, and
the provider-backed `all_in_total_minor` remains null with budget `not_verified`.
Nothing is booked. Route times are walking estimates, not transit schedules or
accessibility guarantees. Venue data may be incomplete or stale.

The offline, fully costed fixture demonstration remains at `/demo`; its endpoint
and deterministic validator are unchanged. Live failures never substitute mock
places. Research/RAG remains available separately, not an inventory authority.

## User-entered travel window and cost checks

The next user-approved slice adds a collapsed optional form section. The API's
`LivePlanRequest` extends the old request without changing `/plan` or `/demo`:

- `travel_times`: arrival time on `start_date`, departure time on `end_date`,
  both destination-local clock times, plus `transfer_buffer_minutes` (0–240,
  default 60). Both times are required when the object is supplied.
- `cost_estimates`: transport, accommodation, activities, meals, and fees/taxes,
  each nullable non-negative integer minor units. All values are **whole-trip
  totals for all travellers** in the request currency. There is no implicit
  per-person/per-night multiplication or currency conversion. Blank is unknown;
  explicit zero is allowed but represents the user's assumption, not free
  admission verified by the provider. Do not double-count taxes.

Pure `domain/live_constraints.py` resolves local times against the provider's
IANA timezone. Nonexistent/ambiguous clock-change times are rejected rather than
guessed. Transfer buffers are elapsed minutes after arrival and before departure;
the global usable window constrains every activity, including cross-midnight
buffers and partial days. Reversed/empty windows return `invalid_window` after
city lookup, without spending further calls on places/matrices. A valid but too
short window returns no visits, never relaxes constraints. The default buffer
is a visible user-adjustable allowance, not a computed airport/station transfer.

Pure integer arithmetic checks the five category totals against the all-in
budget. `budget_estimate` separately reports provenance (`user_entered` basis),
category values, known subtotal, missing categories, total when complete, and
remaining amount only when complete. Status is `incomplete`,
`within_entered_estimate`, or `over_entered_estimate`. If even the known subtotal
exceeds budget, the API returns `budget_exceeded` with no itinerary and makes
**no provider calls**. Equality to budget passes the entered-estimate check only.
Known costs are not reassigned to individual venues or used to claim an actual
all-in trip price. Supplied costs remain visible even if live retrieval fails.

Each entered category and budget is capped at 1,000,000,000,000 minor units;
five-category sums stay safely within the frontend's exact integer range.
Strict schemas reject floats, booleans, unknown fields and offset clock times.
The response's separate `travel_window` contains aware resolved timestamps,
buffer and user-entered provenance. No information is persisted. Editing the
form clears a prior live result, and stale in-flight results are not displayed.

Passing these checks means only that the provisional activity schedule fits
the supplied travel window and the supplied estimates fit the budget. It does
not establish ticket validity, departure punctuality, hotel availability, venue
opening hours, actual prices, meal timing or a fully validated live trip.

## Local setup and secrets

Put `TRIPPILOT_GEOAPIFY_API_KEY=your_key` in the gitignored `backend/.env`, or set
that variable in the backend process environment. The environment wins. The
loader reads **only that named variable**, accepts optional surrounding quotes,
does not execute dotenv content or expand shell expressions, and does not load
OpenAI settings. Existing backend/frontend startup commands still apply.

The key stays on the server in an `x-api-key` header. It is never inserted in a
URL, browser response or frontend bundle. Do not log provider headers, raw
exceptions or dotenv content. Tests use fake keys and an HTTP mock transport.
No new dependency or paid LLM call is required.

## MCP, validation and resource limits

Only `https://api.geoapify.com/v1/mcp` is contacted, through documented JSON-RPC
`tools/call` requests, protocol version 2025-06-18. Tool names and parameters are
built by application code; users/models cannot supply arbitrary tools or URLs.
The allowlist is `geocode_address`, `search_places`, `calculate_route_matrix`.
The remote provider documents session initialization as optional; tool schemas
were checked using authenticated `tools/list` during implementation.

The protocol envelope and matrix are strict extra-forbid Pydantic schemas.
Geoapify's extensible city/place metadata is treated as JSON and explicitly
projected into small strict records: IDs, labels, coordinates and timezone.
Other vendor fields are neither executed nor rendered. Source labels are plain
React text; map links are constructed with validated numeric coordinates on a
fixed OpenStreetMap origin. The response retains IDs, UTC retrieval time and
Geoapify/OpenStreetMap attribution. No provider-supplied link is followed.

- At most five tool calls: one geocode, up to three searches (20 results each),
  and one walking matrix (at most 8×8). No retries.
- At most 500 KB decoded per response, 3-second individual HTTP timeout,
  8-second absolute live service deadline under 10-second HTTP middleware.
- HTTP redirects and environment proxies disabled; failures become safe states.
- One live request in flight, with at least 210 ms between tool requests.
- Twenty attempts per UTC day per backend process. At the documented credit
  rules this reserves at most about 1,360 credits/day in this process, below
  the free plan's 3,000 daily credits. Failed attempts also consume the local
  allowance. **This is not a durable account-wide quota:** restart/reload resets
  it, other applications/processes consume the same provider allowance, and
  the provider's own enforcement remains authoritative. Use one local worker.
- No production deployment, durable cache, persistence, autonomous runtime
  agent or payment mechanism is added. Confirm provider plan limits before
  scaling or enabling billing. MCP is the tool protocol, not an LLM brain.

## Verification and next work

Offline checks cover day bounds, timezone/DST, unique places, positive visits,
rounded route gaps, missing/unreachable routes, strict schema errors, ambiguous
cities, fixed-origin/auth-header transport, oversized replies, tool limits,
safe errors, missing configuration and local allowance. Frontend guards reject
invented prices/validity and malformed results; the main form uses the live
endpoint while the demo keeps its old contract.

Live smoke: Toronto, October 10–11, 2026 returned six real museum/park stops
with walking estimates (2–6 minutes between selected stops), destination timezone
America/Toronto and budget explicitly unverified. No paid LLM was called.
The main browser form also returned six Montreal stops for those dates, including
Musée McCord Stewart, Barbie Expo and Square Dorchester. The result received
keyboard focus. At 390 CSS pixels the document width was 390 pixels, with no
horizontal overflow. Native browser zoom is not claimed as tested.

Verification: 417 backend tests and 74 frontend tests, Ruff, Pyright, ESLint,
TypeScript, Prettier and the production build. No package/lockfile or runtime
dependency changes were required.

Travel-window/entered-cost follow-up verification: 446 backend and 83 frontend
tests passed, along with the same static checks, formatting and production
build. The main browser form generated a Montreal draft for October 10–11:
arrival 13:00, departure 12:00 and 60-minute buffers resolved to an activity
window of 14:00 on the first day through 11:00 on the last. All three returned
visits stayed inside it. CAD 470 in entered category totals against a CAD 500
budget displayed CAD 30 remaining, labelled as user estimates. Tests additionally
cover equality/excess by one minor unit, incomplete costs, explicit zero,
no traveller multiplication, reversed/too-short windows, cross-midnight buffers,
and nonexistent/ambiguous DST times. No paid LLM calls or new dependencies.

Next: source date-specific transport schedules and reliable venue hours. Free
VIA GTFS can support rail timetables but does not include fares. Hotel and
intercity quotes need a separate provider/access decision. Do not call this
slice a fully live, all-in validated itinerary until those gaps are closed.

References: [Geoapify MCP](https://apidocs.geoapify.com/docs/mcp/),
[free-plan limits](https://www.geoapify.com/pricing/),
[route matrix credits](https://apidocs.geoapify.com/docs/route-matrix/),
[OpenStreetMap attribution](https://www.openstreetmap.org/copyright).
