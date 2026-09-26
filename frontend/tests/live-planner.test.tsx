import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createLivePlan,
  isLiveDraft,
  type LiveDraft,
} from "@/lib/live-planner";
import { LiveResult } from "@/components/LiveResult";
import { TripPlanner } from "@/components/TripPlanner";

const draft: LiveDraft = {
  status: "draft",
  city: {
    place_id: "city-1",
    name: "Toronto, ON, Canada",
    timezone: "America/Toronto",
    lat: 43.65,
    lon: -79.38,
  },
  destination_choices: [],
  stops: [
    {
      place: {
        place_id: "place-1",
        name: "Live Park",
        address: "Toronto",
        category: "leisure.park",
        lat: 43.65,
        lon: -79.38,
      },
      day: "2026-10-10",
      start: "2026-10-10T09:00:00-04:00",
      end: "2026-10-10T10:00:00-04:00",
      walking_minutes_from_previous: null,
      visit_duration_basis: "estimated_60_minutes",
      opening_hours_status: "unverified",
      price_minor: null,
    },
  ],
  retrieved_at: "2026-09-26T12:00:00Z",
  budget_status: "not_verified",
  all_in_total_minor: null,
  notice: "Incomplete live draft. Nothing booked.",
  missing: ["Accommodation prices", "Opening hours"],
  attribution: "Geoapify · © OpenStreetMap contributors (ODbL)",
};

afterEach(() => vi.unstubAllGlobals());

describe("live draft contract", () => {
  it("accepts source-backed drafts with explicit unknowns", () => {
    expect(isLiveDraft(draft)).toBe(true);
  });
  it.each([
    { ...draft, all_in_total_minor: 0 },
    { ...draft, budget_status: "passed" },
    { ...draft, extra: "unexpected" },
    { ...draft, city: null },
    { ...draft, stops: [] },
    { ...draft, stops: [draft.stops[0], draft.stops[0]] },
    { ...draft, stops: [{ ...draft.stops[0], price_minor: 0 }] },
    {
      ...draft,
      stops: [{ ...draft.stops[0], walking_minutes_from_previous: -1 }],
    },
  ])("rejects fabricated completeness and malformed data", (value) => {
    expect(isLiveDraft(value)).toBe(false);
  });
  it("does not hide unknown costs or opening hours", () => {
    render(<LiveResult result={draft} />);
    expect(
      screen.getByText("Budget not verified · Total unknown"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Opening hours unverified · Price unknown"),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", {
      name: "View location on OpenStreetMap",
    });
    expect(link.getAttribute("href")).toMatch(
      /^https:\/\/www.openstreetmap.org\//,
    );
    expect(screen.getByRole("region")).toHaveFocus();
  });
  it("uses only the live endpoint and sends no key", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => draft });
    vi.stubGlobal("fetch", fetcher);
    await createLivePlan({
      origin: "Kingston",
      destination: "Toronto",
      start_date: "2026-10-10",
      end_date: "2026-10-10",
      travellers: 1,
      total_budget_minor: 10000,
      currency: "CAD",
      interests: ["nature"],
      pace: "balanced",
      earliest_activity_time: "09:00",
    });
    expect(fetcher.mock.calls[0][0]).toMatch(/\/itineraries\/live-plan$/);
    expect(fetcher.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
    });
  });
  it("main live form submits and does not offer the mock coordinator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => draft }),
    );
    const user = userEvent.setup();
    render(<TripPlanner live />);
    expect(
      screen.queryByText("Try coordinator-assisted experiment"),
    ).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Origin"), "Kingston, Ontario");
    await user.type(
      screen.getByLabelText("Destination city"),
      "Toronto, Ontario, Canada",
    );
    await user.type(screen.getByLabelText("Start date"), "2026-10-10");
    await user.type(screen.getByLabelText("End date"), "2026-10-11");
    await user.type(screen.getByLabelText("Total budget"), "500");
    await user.click(screen.getByLabelText("Nature"));
    await user.click(screen.getByRole("button", { name: "Create live draft" }));
    expect(await screen.findByText("Live Park")).toBeInTheDocument();
  });
});
