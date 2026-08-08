import type {
  CoordinatorPlanResponse,
  PlanningFailure,
  PlanningSuccess,
} from "@/lib/api-types";

const request = {
  origin: "Kingston, Ontario",
  destination: "Toronto, Ontario",
  start_date: "2026-08-10",
  end_date: "2026-08-11",
  travellers: 1,
  budget: { amount_minor: 100_000, currency: "CAD" as const },
  interests: ["arts_culture", "student_budget"] as const,
  pace: "balanced" as const,
  earliest_activity_time: "09:00:00",
  destination_timezone: "America/Toronto",
};

const perPerson = {
  basis: "per_person" as const,
  unit_price: { amount_minor: 0, currency: "CAD" as const },
  charged_travellers: 1,
};

export const successResponse: PlanningSuccess = {
  status: "success",
  request: { ...request, interests: [...request.interests] },
  proposed_itinerary: {
    scheduled_items: [
      {
        item_id: "activity-late",
        title: "Harbour walk",
        kind: "activity",
        window: {
          start: "2026-08-10T15:00:00-04:00",
          end: "2026-08-10T16:00:00-04:00",
        },
        location_id: "toronto-harbour",
        location_label: "Toronto Harbour",
        estimated_cost: { amount_minor: 0, currency: "CAD" },
        source_record_id: "mock-activity-harbour",
        pricing: perPerson,
        transport_role: null,
      },
      {
        item_id: "transport-inbound",
        title: "Morning train",
        kind: "transport",
        window: {
          start: "2026-08-10T08:00:00-04:00",
          end: "2026-08-10T10:00:00-04:00",
        },
        location_id: "toronto-station",
        location_label: "Toronto Central Station",
        estimated_cost: { amount_minor: 12_000, currency: "CAD" },
        source_record_id: "mock-train-inbound",
        pricing: {
          ...perPerson,
          unit_price: { amount_minor: 12_000, currency: "CAD" },
        },
        transport_role: "inbound",
      },
      {
        item_id: "activity-early",
        title: "Gallery visit",
        kind: "activity",
        window: {
          start: "2026-08-10T11:00:00-04:00",
          end: "2026-08-10T12:30:00-04:00",
        },
        location_id: "toronto-gallery",
        location_label: "Civic Shapes Gallery",
        estimated_cost: { amount_minor: 2_500, currency: "CAD" },
        source_record_id: "mock-activity-gallery",
        pricing: {
          ...perPerson,
          unit_price: { amount_minor: 2_500, currency: "CAD" },
        },
        transport_role: null,
      },
      {
        item_id: "transport-outbound",
        title: "Evening train home",
        kind: "transport",
        window: {
          start: "2026-08-11T18:00:00-04:00",
          end: "2026-08-11T20:00:00-04:00",
        },
        location_id: "toronto-station",
        location_label: "Toronto Central Station",
        estimated_cost: { amount_minor: 12_000, currency: "CAD" },
        source_record_id: "mock-train-outbound",
        pricing: {
          ...perPerson,
          unit_price: { amount_minor: 12_000, currency: "CAD" },
        },
        transport_role: "outbound",
      },
    ],
    accommodation_stays: [
      {
        stay_id: "stay-one",
        title: "Campus guest house",
        check_in: "2026-08-10T15:00:00-04:00",
        check_out: "2026-08-11T11:00:00-04:00",
        number_of_nights: 1,
        location_id: "campus-stay",
        location_label: "Campus Guest House",
        estimated_cost: { amount_minor: 15_000, currency: "CAD" },
        source_record_id: "mock-stay-campus",
        pricing: {
          basis: "per_group",
          unit_price: { amount_minor: 15_000, currency: "CAD" },
          charged_travellers: null,
        },
      },
    ],
    explicit_fees: [
      {
        fee_id: "fee-tax",
        title: "Mock tax",
        cost: { amount_minor: 1_500, currency: "CAD" },
      },
    ],
    non_blocking_markers: [],
  },
  cost_breakdown: {
    transport: { amount_minor: 24_000, currency: "CAD" },
    accommodation: { amount_minor: 15_000, currency: "CAD" },
    activity: { amount_minor: 2_500, currency: "CAD" },
    meal: { amount_minor: 7_000, currency: "CAD" },
    fees_taxes: { amount_minor: 1_500, currency: "CAD" },
    total_estimated_cost: { amount_minor: 50_000, currency: "CAD" },
  },
  validation_report: { is_valid: true, violations: [] },
  matched_interests: ["arts_culture", "student_budget"],
  planning_rationale: ["Selected a validator-clean mock proposal."],
  assumptions: ["One mock meal estimate is included per usable day."],
  warnings: ["Hours are mock estimates."],
  fixture_snapshot_version: "2026-08-01.v1",
  planner_id: "deterministic-greedy-bounded-v1",
  disclosures: [
    "All prices, schedules, operating hours, and availability are mock estimates.",
    "Nothing has been booked or reserved; verify all details before purchase.",
  ],
};

export const failureResponse: PlanningFailure = {
  status: "planning_failure",
  request: { ...request, interests: [...request.interests] },
  failure_code: "INSUFFICIENT_BUDGET",
  explanation: "Every complete schedulable proposal exceeds the all-in budget.",
  relevant_constraints: ["budget 1000 CAD"],
  validation_report: {
    is_valid: false,
    violations: [
      {
        code: "BUDGET_EXCEEDED",
        message: "Estimated total exceeds the budget.",
        affected_ids: [],
        severity: "error",
      },
    ],
  },
  assumptions: ["Pace may be reduced when budget requires it."],
  warnings: [],
  fixture_snapshot_version: "2026-08-01.v1",
  planner_id: "deterministic-greedy-bounded-v1",
  disclosures: [
    "All prices and schedules are mock estimates.",
    "Nothing has been booked; verify all details before purchase.",
  ],
};

export const coordinatorFallbackResponse: CoordinatorPlanResponse = {
  ...successResponse,
  planner_id: "trippilot-fixed-ranker-v1",
  warnings: [
    "The extra preferences could not be applied. TripPilot selected a validated proposal using its deterministic fallback.",
  ],
  experiment: {
    contract_version: "coordinator-experiment-v1",
    approach: "deterministic_fallback",
    interpreted_preference_tags: [],
    selection_facts: ["lowest_estimated_cost", "shortest_transfer_time"],
    fallback_code: "MODEL_NOT_CONFIGURED",
  },
};
