# Design System

## 1. Product experience principles

The future interface should feel practical, calm, and student-friendly. It must
make constraints, costs, and uncertainty easy to scan rather than presenting an
itinerary as magical or authoritative.

- Constraints first: keep budget, dates, pace, and earliest start visible.
- Honest confidence: label mock data, estimates, assumptions, and warnings.
- Actionable errors: identify the conflicting input and suggest a safe change.
- Progressive detail: show the daily plan first, with rationale and provenance
  available without crowding the page.
- Accessible by default: keyboard support, semantic structure, visible focus,
  sufficient contrast, and non-color status cues.

## 2. Voice and terminology

Use concise, direct, non-judgmental language.

Preferred terms:

- “Proposed itinerary” rather than “Your booking.”
- “Estimated total” rather than “Final price.”
- “Mock data” and “Verify before purchase.”
- “Could not create a valid plan” rather than silently relaxing constraints.
- “Consider increasing the budget” rather than “Your budget is too low.”

Never use “booked,” “confirmed,” “reserved,” “guaranteed,” or “live price” unless
a future product has actually completed and verified that action.

## 3. Information architecture

The initial UI should be one responsive planning flow:

1. **Trip details:** origin, destination, dates, travellers.
2. **Constraints:** budget/currency, pace, earliest activity time.
3. **Interests:** selectable tags.
4. **Review:** summarized inputs and generate action.
5. **Result:** constraint summary, day cards, cost breakdown, assumptions,
   warnings, and mock-data/no-booking disclosure.

Keep the user's inputs available when generation fails so constraints can be
adjusted without re-entry.

## 4. Visual foundation

These are semantic starting tokens, not a finalized brand:

| Token | Suggested value | Purpose |
| --- | --- | --- |
| `color.brand` | `#176B5B` | Primary actions and highlights |
| `color.accent` | `#E9A23B` | Selected interests and budget emphasis |
| `color.canvas` | `#F7F8F5` | Page background |
| `color.surface` | `#FFFFFF` | Cards and form sections |
| `color.text` | `#17201E` | Primary text |
| `color.muted` | `#586864` | Secondary text |
| `color.danger` | `#B42318` | Errors and hard violations |
| `color.warning` | `#9A6700` | Estimates and cautions |
| `color.success` | `#16794B` | Validated state |
| `radius.sm/md/lg` | `6/10/16px` | Controls, cards, feature surfaces |
| `space.1–8` | `4–32px` | Four-pixel spacing scale |

Use a readable system sans-serif stack for UI text and tabular numerals for
money and times. Do not rely on decorative travel imagery for essential meaning.
Verify WCAG 2.2 AA contrast before implementation; suggested colors are not a
substitute for testing.

## 5. Core components

- `TripForm` with grouped fields and inline validation.
- `PlaceField` for plain MVP place labels; no implied live autocomplete.
- `DateRangeField` that explains the one-to-four-day inclusive rule.
- `MoneyField` pairing amount and currency.
- `InterestPicker` using keyboard-accessible toggles.
- `PaceSelector` with a short description of each pace.
- `ConstraintSummary` displayed before and after planning.
- `DayCard` containing a chronological timeline.
- `ScheduledItem` with type, time, location, cost, and source label for
  time-blocking activities, meals, and transport.
- `AccommodationStay` shown separately from the chronological timeline.
- `CostBreakdown` with the all-in total for all travellers, transport,
  accommodation, activity, meal, and fee/tax category totals, budget, and
  remaining amount.
- `ValidationNotice` for hard violations and suggested constraint changes.
- `EstimateBanner` persistently marking mock data and the no-booking status.

## 6. Status patterns

- **Valid proposal:** green icon plus text “Constraints validated”; this does not
  mean booked or currently available.
- **Warning:** amber icon plus plain-language assumption or estimate.
- **Invalid/no plan:** red icon plus violation summary and affected fields.
- **Loading:** describe the current synchronous planning step and preserve layout;
  do not invent progress percentages.
- **Empty:** explain which inputs are needed to generate a proposal.

All statuses require text and an icon, not color alone.

## 7. Responsive and accessible behavior

- Start with a single-column mobile layout and introduce a result summary rail on
  wider screens.
- Maintain logical heading order and landmark regions.
- Associate errors and hints programmatically with their fields.
- Move focus to the error summary after failed submission and provide links back
  to invalid fields.
- Use native controls where possible, minimum practical touch targets, and
  reduced-motion support.
- Format dates, times, and currency visibly while preserving normalized values at
  the API boundary.

## 8. Content examples

Disclosure:

> This is a proposed itinerary built from mock data. Prices, hours, and
> availability are estimates. Nothing has been booked.

Constraint failure:

> We couldn't create a valid plan within CAD 180. The least expensive mock
> options total CAD 214. Consider increasing the budget or shortening the trip.

Avoid vague failures such as “Something went wrong” when a safe, structured
domain reason is available.

## 9. Decisions for UI implementation

- Final brand identity, typeface, and illustration direction.
- Whether the first Next.js experience is a single page or short stepper.
- Display convention for taxes and category estimates.
- Map usage; no map is required for the first MVP.
- Localization and bilingual English/French support timeline.
