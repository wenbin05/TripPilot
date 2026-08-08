# Product and UX Benchmark

## 1. Purpose and method

This benchmark informs TripPilot's product positioning and interface density
before the coordinator experiment is implemented. It is a point-in-time review
of public product pages and interfaces observed on 2026-08-03. Capabilities and
screens may change.

The comparison deliberately focuses on useful patterns rather than feature
parity. Booking, payments, authentication, live providers, collaboration, maps,
multi-city travel, and reservation management remain outside TripPilot's MVP.

## 2. Reference products

| Product | Public positioning and interaction pattern | Useful reference | Do not copy into this MVP |
| --- | --- | --- | --- |
| [Wanderlog](https://wanderlog.com/trip-planner-ai) | Broad organizer combining AI suggestions, daily itineraries, maps, route optimization, budgeting, reservations, and collaboration | Keep itinerary, route feasibility, and budget information connected; make daily structure immediately scannable | Its many workspace modes and travel-management features would overload TripPilot's bounded student flow |
| [Mindtrip](https://mindtrip.ai/) | Conversation-led planning with preference-rich prompts, recommendation cards, maps, reviews, collections, and collaboration | Let users express priorities naturally and keep a short reason or evidence close to a recommendation | A persistent chat, media feed, imports, group features, and commerce would hide hard constraints and create visual noise |
| [Tripadvisor Trips](https://www.tripadvisor.com/Trips) ([AI planning launch](https://tripadvisor.mediaroom.com/Tripadvisor-launches-AI-powered-travel-planning-product)) | AI recommendations combined with saved places, community content, collaboration, and trip organization | Keep provenance and recommendation evidence available near the itinerary | TripPilot does not have Tripadvisor's review corpus, discovery inventory, or surrounding booking marketplace |
| [Layla](https://layla.ai/) | A very low-friction conversational entry point centered on travel style and budget, followed by refinement and broader travel-agent services | Use one strong proposition and one obvious starting action; keep optional preference capture approachable | Live prices, availability, bookings, human agents, multi-city planning, inspirational galleries, and multiple prompt shortcuts are outside scope |
| [Tripomatic](https://tripomatic.com/en/features/trip-itinerary-planner) | A day-by-day editor connected to a map, realistic travel times, ordering, and a shortlist | Preserve day-by-day chronology, visually separate movement from activities, and make schedule realism easy to judge | A live map, drag-and-drop editor, global place inventory, tickets, exports, and a shortlist are not required for the first experiment |

Supplementary pattern checks included
[Roadtrippers' progressive planning flow](https://support.roadtrippers.com/hc/en-us/articles/203322709-Website-Getting-Started)
and TripIt's official guidance on
[chronological item ordering](https://help.tripit.com/en/support/solutions/articles/103000063326-reorder-trip-items)
and its [accessibility-oriented web
redesign](https://www.tripit.com/web/blog/news-culture/tripit-web-experience).
They reinforce progressive disclosure, chronological scanning, streamlined
navigation, and keyboard/screen-reader support. TripPilot's true single-column
mobile reading mode is our responsive design conclusion, not a competitor claim.

These public products compete mainly through broad travel organization,
real-world content and commerce, or conversational inspiration. TripPilot's
credible differentiation is narrower: a one-to-four-day student trip whose
hard constraints, all-in budget, provenance, estimate status, and no-booking
boundary are visible and deterministically checked. This is an inference from
the cited public positioning, not a claim about undisclosed competitor systems.

## 3. Product decisions from the benchmark

- Keep the structured planner as the primary shell. Optional preference notes
  add conversational expressiveness without adding chat history or chat chrome.
- Show one recommended proposal. Internal coordinator candidates, rank scores,
  schemas, retries, and validator traffic are not user interface concepts.
- Keep one primary action per state: create, edit and regenerate, or correct a
  specific error. Do not add competing save, share, book, map, export, or explore
  actions.
- Keep the day-by-day itinerary and all-in student budget in the same reading
  flow. Do not make users switch modes to understand feasibility and cost.
- Put a concise server-derived “Why this plan?” summary near the result. Keep
  detailed provenance available through progressive disclosure rather than
  repeating source metadata throughout the primary scan path.
- Preserve the existing prominent estimate/no-booking disclosure. Competitor
  live-price or reservation language is not applicable to mock data.
- Treat edit-and-regenerate as the only initial refinement loop. Do not add a
  conversational revision thread or silently mutate a validated proposal.

## 4. Current TripPilot interface audit

The current interface already has a calm visual system, plain language, strong
field grouping, accessible native controls, one primary submit action, and a
prominent mock-data/no-booking notice. It avoids the marketplace and discovery
clutter visible in broader travel products.

The main opportunity is density, not a visual redesign. At a 1280 × 720 desktop
viewport, the header, disclosure, and large hero consume most of the first
screen and only the beginning of Trip details is visible. The four large stacked
cards also introduce substantial vertical whitespace, especially around pace
and review. This makes a small, bounded form feel longer than it is.

The current result component also exposes raw location IDs and mock source IDs
inside every scheduled-item card, while fixture and planner identifiers occupy
the visible proposal rail. This is traceable but not user-centered: repeated
technical identifiers compete with time, title, category, and cost. They should
remain available in one expandable technical/provenance area rather than the
default timeline scan.

The next UI refinement should therefore:

- reduce the desktop hero to a compact product introduction so origin,
  destination, and date controls begin in the first viewport;
- retain the disclosure near the top but reduce its vertical footprint;
- use a compact two-column desktop planner with the editable fields as the main
  column and a sticky review/action summary as the secondary column;
- keep a single-column mobile flow in the same semantic order;
- present pace as three compact, fully described choices instead of a tall
  vertical block where space permits;
- keep helper text to one useful line and remove repeated explanations that do
  not change a decision;
- replace the large standalone Review card on desktop with the summary rail,
  while retaining an inline Review section on small screens; and
- never reduce touch targets, visible focus, labels, error associations, or
  status text in pursuit of density.

The desktop rail and mobile inline review are one semantic region and one submit
control rearranged with CSS. They are not duplicate responsive DOM trees.

## 5. Clean-interface contract

### Planning state

- One page, one form, four semantic sections, and one dominant create action.
- No map, chat transcript, image gallery, recommendations feed, account prompt,
  or booking action.
- At a 1280 × 720 CSS viewport at 100% zoom, the initial viewport shows the disclosure, concise value
  proposition, and the origin/destination row plus at least the start of date
  entry without scrolling.
- At widths of 768 CSS px and below, controls use one column and no horizontal
  scrolling is required at 320 CSS px. Separately verify reflow and text
  visibility at 200% browser zoom.
- Optional coordinator controls remain visually subordinate to the required
  structured inputs and are collapsed while opt-in is off.
- The review summary uses short labels and values; it does not repeat helper
  text or technical validation language.

### Result state

- A short context line contains route and dates. The result heading is followed
  by an at-a-glance row with no more than four values: validation status, trip
  length, all-in estimated total, and remaining budget. Planning approach is a
  secondary proposal detail.
- The day-by-day schedule is the primary content. Transport, meal, and activity
  items use distinct text/icon treatment; accommodation remains outside the
  timed schedule.
- A timeline row initially shows time, item type/title, a human-readable
  location/place label, and estimated cost. The label is derived server-side
  from canonical provider records, never model prose. Raw location and source
  IDs move to expandable provenance details that preserve an explicit
  item-to-source mapping; raw fixture and planner IDs never occupy the default
  result view.
- Category totals remain visible near the all-in total. Detailed cost rows,
  non-actionable assumptions, informational warnings, provenance, and “Why this
  plan?” may expand without displacing the day plan from the main reading path.
  Actionable warnings affecting feasibility, estimates, or required user
  verification remain visible beside validation and budget status.
- The first result viewport at a 1280 × 720 CSS viewport and 100% zoom shows the
  status, route, all-in total, disclosure, and beginning of Day 1.
- On mobile, show the compact validation and budget summary before the day cards;
  do not place essential cost comprehension after the full itinerary.
- No more than one high-emphasis primary action is visible in the result header.
  Editing trip details is the refinement path.
- Coordinator fallback appears as one concise warning; it does not create a
  second result, modal, chat message, or retry control.

### Content hierarchy

Every visible element should answer one of four user questions:

1. What did I ask for?
2. Does the proposal meet the hard constraints?
3. What happens each day and what does it cost?
4. What is estimated, why was this selected, and what should I verify?

Content that does not answer one of these questions is removed from the primary
flow or placed in progressive disclosure.

## 6. Usability benchmark and gates

Run a moderated test with five to eight university students before enabling the
coordinator UI. Each participant must:

1. create a two-day Toronto proposal under a stated all-in budget;
2. identify whether the plan passed hard constraints;
3. identify the estimated total, remaining budget, and largest cost category;
4. explain whether anything was booked and what must be verified;
5. find why one recommendation fits the request; and
6. edit one preference and regenerate.

Record completion, time on task, form validation errors, first-scroll position,
preference-fit rating, budget-comprehension accuracy, disclosure comprehension,
edit-and-regenerate success, and qualitative clutter/confidence feedback.

UI approval requires:

- 100% of participants understand that nothing was booked;
- 100% correctly locate the estimated total and category breakdown;
- at least 80% identify validation status, estimated total, remaining budget,
  and Day 1's first activity within five seconds;
- at least 80% complete all six tasks without facilitator correction;
- median first-plan form completion within two minutes using the supported
  fixture scenario;
- average clarity of at least 4.0/5 and average visual satisfaction of at least
  4.0/5, scored as separate questions;
- no participant reports that a technical coordinator term is required to use
  the product; and
- no critical accessibility defect: the full keyboard path works; focus order
  and visibility are logical; controls, descriptions, and errors have
  programmatic relationships; loading/results are announced; contrast meets
  WCAG 2.2 AA; 200% zoom reflows without lost content; and 320 CSS px has no
  horizontal page overflow.

These usability gates complement rather than replace the deterministic and
coordinator release gates.
