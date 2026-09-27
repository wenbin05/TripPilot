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
import { INITIAL_LIVE_OPTIONS, toLiveInputs } from "@/lib/live-inputs";

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
  budget_estimate: null,
  travel_window: null,
  notice: "Incomplete live draft. Nothing booked.",
  missing: ["Accommodation prices", "Opening hours"],
  attribution: "Geoapify · © OpenStreetMap contributors (ODbL)",
};

afterEach(() => vi.unstubAllGlobals());

describe("live draft contract", () => {
  const estimate = {
    basis: "user_entered_all_travellers_whole_trip" as const,
    currency: "CAD" as const,
    budget_minor: 50000,
    categories: {
      transport: 10000,
      accommodation: 20000,
      activities: 0,
      meals: 15000,
      fees_taxes: 5000,
    },
    status: "within_entered_estimate" as const,
    known_subtotal_minor: 50000,
    estimated_total_minor: 50000,
    remaining_minor: 0,
    missing_categories: [],
  };
  it("checks entered estimates without changing provider-verified status", () => {
    expect(isLiveDraft({ ...draft, budget_estimate: estimate })).toBe(true);
    expect(
      isLiveDraft({
        ...draft,
        budget_estimate: { ...estimate, estimated_total_minor: 49999 },
      }),
    ).toBe(false);
    render(<LiveResult result={{ ...draft, budget_estimate: estimate }} />);
    expect(
      screen.getByText("Within budget based on your estimates"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Not provider quotes/)).toBeInTheDocument();
  });
  it("rejects drafts outside the entered travel window", () => {
    const window = {
      basis: "user_entered",
      arrival: "2026-10-10T12:00:00-04:00",
      departure: "2026-10-10T18:00:00-04:00",
      available_from: "2026-10-10T13:00:00-04:00",
      available_until: "2026-10-10T17:00:00-04:00",
      transfer_buffer_minutes: 60,
    };
    expect(isLiveDraft({ ...draft, travel_window: window })).toBe(false);
  });
  it("preserves unknowns and treats an explicit zero as an estimate", () => {
    expect(toLiveInputs(INITIAL_LIVE_OPTIONS)).toEqual({
      travel_times: null,
      cost_estimates: null,
    });
    const value = toLiveInputs({
      ...INITIAL_LIVE_OPTIONS,
      costs: { ...INITIAL_LIVE_OPTIONS.costs, activities: "0", meals: "10.01" },
    });
    expect(value.cost_estimates).toEqual({
      transport: null,
      accommodation: null,
      activities: 0,
      meals: 1001,
      fees_taxes: null,
    });
  });
  it.each(["-1", "1.111", "1e3", "10000000001"])(
    "rejects invalid cost %s",
    (value) => {
      expect(() =>
        toLiveInputs({
          ...INITIAL_LIVE_OPTIONS,
          costs: { ...INITIAL_LIVE_OPTIONS.costs, meals: value },
        }),
      ).toThrow();
    },
  );
  it("requires paired times and whole-minute bounded buffers", () => {
    expect(() =>
      toLiveInputs({ ...INITIAL_LIVE_OPTIONS, arrivalTime: "12:00" }),
    ).toThrow(/both/);
    expect(() =>
      toLiveInputs({
        ...INITIAL_LIVE_OPTIONS,
        arrivalTime: "12:00",
        departureTime: "18:00",
        bufferMinutes: "1.5",
      }),
    ).toThrow(/whole number/);
    expect(
      toLiveInputs({
        ...INITIAL_LIVE_OPTIONS,
        arrivalTime: "12:00",
        departureTime: "18:00",
      }).travel_times?.transfer_buffer_minutes,
    ).toBe(60);
  });
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
    await user.type(screen.getByLabelText("Total budget"), "0");
    expect(screen.queryByText("Live Park")).not.toBeInTheDocument();
  });
  it("serializes optional travel times and category totals from the form", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => draft });
    vi.stubGlobal("fetch", fetcher);
    const user = userEvent.setup();
    render(<TripPlanner live />);
    await user.type(screen.getByLabelText("Origin"), "Kingston, Ontario");
    await user.type(
      screen.getByLabelText("Destination city"),
      "Toronto, Ontario",
    );
    await user.type(screen.getByLabelText("Start date"), "2026-10-10");
    await user.type(screen.getByLabelText("End date"), "2026-10-11");
    await user.type(screen.getByLabelText("Total budget"), "500");
    await user.click(screen.getByLabelText("Nature"));
    await user.click(
      screen.getByText("Travel times and cost estimates (optional)"),
    );
    await user.type(
      screen.getByLabelText("Arrival time on first day"),
      "13:00",
    );
    await user.type(
      screen.getByLabelText("Departure time on last day"),
      "12:00",
    );
    await user.type(screen.getByLabelText("Activities (whole trip)"), "0");
    await user.type(screen.getByLabelText("Meals (whole trip)"), "100.01");
    await user.click(screen.getByRole("button", { name: "Create live draft" }));
    await screen.findByText("Live Park");
    const sent = JSON.parse(fetcher.mock.calls[0][1].body);
    expect(sent.travel_times).toEqual({
      arrival_time: "13:00",
      departure_time: "12:00",
      transfer_buffer_minutes: 60,
    });
    expect(sent.cost_estimates).toEqual({
      transport: null,
      accommodation: null,
      activities: 0,
      meals: 10001,
      fees_taxes: null,
    });
  });
});
