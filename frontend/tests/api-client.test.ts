import { afterEach, describe, expect, it, vi } from "vitest";
import { createCoordinatorPlan, createPlan } from "@/lib/api-client";
import type { CoordinatorPlanRequest, TripPlanRequest } from "@/lib/api-types";
import {
  coordinatorFallbackResponse,
  failureResponse,
  successResponse,
} from "./fixtures";

const request: TripPlanRequest = {
  origin: "Kingston, Ontario",
  destination: "Toronto, Ontario",
  start_date: "2026-08-10",
  end_date: "2026-08-11",
  travellers: 1,
  total_budget_minor: 100_000,
  currency: "CAD",
  interests: ["arts_culture"],
  pace: "balanced",
  earliest_activity_time: "09:00:00",
};
const coordinatorRequest: CoordinatorPlanRequest = {
  ...request,
  preference_notes: "Prefer quieter stays",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function respondWith(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

describe("createPlan response boundary", () => {
  it.each([successResponse, failureResponse])(
    "accepts a complete $status response",
    async (response) => {
      respondWith(response);
      await expect(createPlan(request)).resolves.toEqual(response);
    },
  );

  it.each([
    { status: "success" },
    { ...successResponse, matched_interests: ["unsupported"] },
    {
      ...successResponse,
      request: {
        ...successResponse.request,
        destination_timezone: "Not/A-Timezone",
      },
    },
    {
      ...successResponse,
      validation_report: {
        is_valid: false,
        violations: [],
      },
    },
    {
      ...successResponse,
      validation_report: {
        is_valid: true,
        violations: [failureResponse.validation_report.violations[0]],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            window: { start: "not-a-timestamp", end: "also-invalid" },
          },
        ],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            location_label: "   ",
          },
        ],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            location_label: 42,
          },
        ],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            location_label: null,
          },
        ],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        accommodation_stays: [
          {
            ...successResponse.proposed_itinerary.accommodation_stays[0],
            location_label: false,
          },
        ],
      },
    },
    {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            location_label: undefined,
          },
        ],
      },
    },
    { ...failureResponse, validation_report: undefined },
    {
      ...failureResponse,
      validation_report: {
        ...failureResponse.validation_report,
        is_valid: true,
      },
    },
    {
      ...failureResponse,
      validation_report: {
        ...failureResponse.validation_report,
        violations: [
          {
            ...failureResponse.validation_report.violations[0],
            code: "UNKNOWN_VIOLATION",
          },
        ],
      },
    },
    { ...failureResponse, failure_code: "UNKNOWN_FAILURE" },
  ])("rejects a malformed 200 response safely", async (response) => {
    respondWith(response);
    await expect(createPlan(request)).rejects.toMatchObject({
      kind: "unexpected",
    });
  });

  it("accepts an explicitly absent location ID and label", async () => {
    const response = {
      ...successResponse,
      proposed_itinerary: {
        ...successResponse.proposed_itinerary,
        scheduled_items: [
          {
            ...successResponse.proposed_itinerary.scheduled_items[0],
            location_id: null,
            location_label: null,
          },
        ],
      },
    };
    respondWith(response);
    await expect(createPlan(request)).resolves.toEqual(response);
  });

  it("rejects malformed 422 details as an unexpected response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "error",
            error_code: "REQUEST_VALIDATION_ERROR",
            explanation: "Invalid request.",
            details: [null],
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(createPlan(request)).rejects.toMatchObject({
      kind: "unexpected",
    });
  });

  it("rejects coordinator metadata on the standard endpoint", async () => {
    respondWith(coordinatorFallbackResponse);

    await expect(createPlan(request)).rejects.toMatchObject({
      kind: "unexpected",
    });
  });
});

describe("createCoordinatorPlan response boundary", () => {
  it("uses the isolated endpoint and accepts strict experiment metadata", async () => {
    respondWith(coordinatorFallbackResponse);

    await expect(createCoordinatorPlan(coordinatorRequest)).resolves.toEqual(
      coordinatorFallbackResponse,
    );
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/itineraries/coordinate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(coordinatorRequest),
      }),
    );
  });

  it.each([
    { ...coordinatorFallbackResponse, experiment: undefined },
    {
      ...coordinatorFallbackResponse,
      experiment: {
        ...coordinatorFallbackResponse.experiment,
        contract_version: "stale-contract",
      },
    },
    {
      ...coordinatorFallbackResponse,
      experiment: {
        ...coordinatorFallbackResponse.experiment,
        selection_facts: ["invented_fact"],
      },
    },
    {
      ...coordinatorFallbackResponse,
      experiment: {
        ...coordinatorFallbackResponse.experiment,
        selection_facts: ["lowest_estimated_cost", "lowest_estimated_cost"],
      },
    },
    {
      ...coordinatorFallbackResponse,
      experiment: {
        ...coordinatorFallbackResponse.experiment,
        approach: "coordinator_assisted",
        fallback_code: "MODEL_TIMEOUT",
      },
    },
  ])("rejects malformed experiment metadata", async (response) => {
    respondWith(response);

    await expect(
      createCoordinatorPlan(coordinatorRequest),
    ).rejects.toMatchObject({ kind: "unexpected" });
  });
});
