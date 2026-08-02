import { afterEach, describe, expect, it, vi } from "vitest";
import { createPlan } from "@/lib/api-client";
import type { TripPlanRequest } from "@/lib/api-types";
import { failureResponse, successResponse } from "./fixtures";

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
    { ...failureResponse, validation_report: undefined },
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
});
