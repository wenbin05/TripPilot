# TripPilot local demo

This demo uses synthetic Kingston-to-Toronto travel data for August 10–13,
2026. Use these dates even when demonstrating later: this is a frozen example,
not current travel availability. No key is needed for the standard planner.

## Start

From the repository root, with the existing Python environment installed:

```bash
TRIPPILOT_COORDINATOR_ENABLED=false \
TRIPPILOT_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000 \
.venv/bin/uvicorn trippilot.api.app:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npx --yes npm@11.19.0 ci
npm run build
npm run start -- --hostname 127.0.0.1
```

Open http://127.0.0.1:3000. See the README for first-time environment setup.
Keep the coordinator checkbox off. Stop each server with Ctrl+C when finished.

## Demonstrate

Enter Kingston, Ontario as origin and Toronto, Ontario as destination. Choose
one traveller, CAD 500 total budget, Balanced pace, 09:00 earliest activity,
and Arts Culture, History, and Student Budget interests.

| Start | End | Expected proposal |
| --- | --- | --- |
| 2026-08-10 | 2026-08-10 | 1 day, CAD 93.00 |
| 2026-08-10 | 2026-08-11 | 2 days, CAD 193.00 |
| 2026-08-10 | 2026-08-13 | 4 days, CAD 344.00 |

Point out the constraint status, remaining budget, category totals, daily
timeline, and expandable source details. These are proposals using estimates;
nothing has been booked.

Then set the budget to CAD 1: a structured budget failure replaces the proposal.
Restore CAD 500 to demonstrate recovery. Set the end date to August 14 to show
the linked validation error for exceeding four inclusive days.

## Browser acceptance, September 10, 2026

Reviewed after syncing merged PR #5 at `b308acb`, with the budget-display fix
on `codex/mvp-demo-acceptance`:

- One-, two-, and four-day flows produced the totals above via the live local API.
- CAD 1 failed safely; restoring CAD 500 recovered the proposal.
- Five-day input showed a linked validation error.
- 390 px and 320 px viewports had no horizontal page overflow. The mobile form
  used one column, and result text wrapped within the viewport.
- Desktop form and mobile result screenshots were visually inspected in-browser.
- The budget failure originally exposed minor units as dollars (`budget 100 CAD`
  for CAD 1). The fix formats the amount using integer division/remainder, with
  regression cases for CAD 0.01, CAD 1.00, and CAD 1.23.
- The focused planner/API suite passed 50 tests; Ruff and Pyright passed.

This is an engineering acceptance pass, not a student usability study. A
separate 200% browser-zoom check and independent user feedback remain outstanding.
