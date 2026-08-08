export const SUPPORTED_INTERESTS = [
  "food",
  "arts_culture",
  "nature",
  "history",
  "nightlife",
  "shopping",
  "sports",
  "student_budget",
] as const;

export const SUPPORTED_CURRENCIES = ["CAD", "USD"] as const;
export const SUPPORTED_PACES = ["relaxed", "balanced", "packed"] as const;

export type Interest = (typeof SUPPORTED_INTERESTS)[number];
export type Currency = (typeof SUPPORTED_CURRENCIES)[number];
export type Pace = (typeof SUPPORTED_PACES)[number];
export type ItemKind = "activity" | "meal" | "transport";
export type TransportRole = "inbound" | "outbound" | "local" | null;
export const VIOLATION_CODES = [
  "ORIGIN_REQUIRED",
  "DESTINATION_REQUIRED",
  "ORIGIN_DESTINATION_SAME",
  "TRIP_LENGTH_OUT_OF_RANGE",
  "INVALID_TRAVELLER_COUNT",
  "INVALID_BUDGET",
  "UNSUPPORTED_CURRENCY",
  "INTEREST_REQUIRED",
  "MISSING_BOUNDARY_TRANSPORT",
  "INVALID_TIMEZONE",
  "RECORD_NOT_FOUND",
  "INVALID_TIME_WINDOW",
  "ITEM_OUTSIDE_TRIP",
  "INVALID_ACCOMMODATION_STAY",
  "ITEM_OVERLAP",
  "ACTIVITY_TOO_EARLY",
  "OUTSIDE_OPERATING_WINDOW",
  "INSUFFICIENT_TRANSFER_TIME",
  "ARRIVAL_DEPARTURE_CONFLICT",
  "NEGATIVE_COST",
  "CURRENCY_MISMATCH",
  "PRICING_INCONSISTENT",
  "TOTAL_MISMATCH",
  "BUDGET_EXCEEDED",
] as const;

export type ViolationCode = (typeof VIOLATION_CODES)[number];

export interface Money {
  amount_minor: number;
  currency: Currency;
}

export interface TripPlanRequest {
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  travellers: number;
  total_budget_minor: number;
  currency: Currency;
  interests: Interest[];
  pace: Pace;
  earliest_activity_time: string;
}

export interface CoordinatorPlanRequest extends TripPlanRequest {
  preference_notes: string | null;
}

export interface NormalizedRequest {
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  travellers: number;
  budget: Money;
  interests: Interest[];
  pace: Pace;
  earliest_activity_time: string;
  destination_timezone: string | null;
}

export interface Pricing {
  basis: "per_person" | "per_group";
  unit_price: Money;
  charged_travellers: number | null;
}

export interface ScheduledItem {
  item_id: string;
  title: string;
  kind: ItemKind;
  window: { start: string; end: string };
  location_id: string | null;
  location_label: string | null;
  estimated_cost: Money;
  source_record_id: string | null;
  pricing: Pricing;
  transport_role: TransportRole;
}

export interface AccommodationStay {
  stay_id: string;
  title: string;
  check_in: string;
  check_out: string;
  number_of_nights: number;
  location_id: string | null;
  location_label: string | null;
  estimated_cost: Money;
  source_record_id: string | null;
  pricing: Pricing;
}

export interface ExplicitFee {
  fee_id: string;
  title: string;
  cost: Money;
}

export interface NonBlockingMarker {
  marker_id: string;
  title: string;
  window: { start: string; end: string };
}

export interface ProposedItinerary {
  scheduled_items: ScheduledItem[];
  accommodation_stays: AccommodationStay[];
  explicit_fees: ExplicitFee[];
  non_blocking_markers: NonBlockingMarker[];
}

export interface CostBreakdown {
  transport: Money;
  accommodation: Money;
  activity: Money;
  meal: Money;
  fees_taxes: Money;
  total_estimated_cost: Money;
}

export interface Violation {
  code: ViolationCode;
  message: string;
  affected_ids: string[];
  severity: "error";
}

export interface ValidationReport {
  is_valid: boolean;
  violations: Violation[];
}

interface ResponseBase {
  request: NormalizedRequest;
  validation_report: ValidationReport;
  assumptions: string[];
  warnings: string[];
  fixture_snapshot_version: string | null;
  planner_id: string;
  disclosures: string[];
}

export interface PlanningSuccess extends ResponseBase {
  status: "success";
  proposed_itinerary: ProposedItinerary;
  cost_breakdown: CostBreakdown;
  matched_interests: Interest[];
  planning_rationale: string[];
  fixture_snapshot_version: string;
}

export const PLANNING_FAILURE_CODES = [
  "INVALID_REQUEST",
  "NO_TRANSPORT_OPTION",
  "NO_ACCOMMODATION_OPTION",
  "NO_FEASIBLE_ACTIVITY_SET",
  "INSUFFICIENT_BUDGET",
  "NO_VALID_ITINERARY",
  "UNSUPPORTED_ROUTE",
  "PROVIDER_DATA_INCOMPLETE",
] as const;

export type PlanningFailureCode = (typeof PLANNING_FAILURE_CODES)[number];

export interface PlanningFailure extends ResponseBase {
  status: "planning_failure";
  failure_code: PlanningFailureCode;
  explanation: string;
  relevant_constraints: string[];
}

export type PlanResponse = PlanningSuccess | PlanningFailure;

export const INTERPRETED_PREFERENCE_TAGS = [
  "lower_cost",
  "larger_budget_buffer",
  "fewer_activities",
  "more_activities",
  "shorter_transfers",
  "activity_variety",
  "daytime_focus",
  "evening_focus",
] as const;

export const COORDINATOR_SELECTION_FACTS = [
  "lowest_estimated_cost",
  "largest_budget_buffer",
  "fewest_activities",
  "most_activities",
  "greatest_activity_variety",
  "shortest_transfer_time",
  "greatest_interest_coverage",
  "most_daytime_activities",
  "most_evening_activities",
] as const;

export const COORDINATOR_FALLBACK_CODES = [
  "MODEL_NOT_CONFIGURED",
  "MODEL_TIMEOUT",
  "MODEL_RATE_LIMITED",
  "MODEL_PROVIDER_ERROR",
  "MODEL_REFUSAL",
  "MODEL_OUTPUT_INVALID",
  "MODEL_ABSTAINED",
  "UNKNOWN_CANDIDATE",
  "CANDIDATE_REVALIDATION_FAILED",
  "DEADLINE_RESERVE_REACHED",
] as const;

export type InterpretedPreferenceTag =
  (typeof INTERPRETED_PREFERENCE_TAGS)[number];
export type CoordinatorSelectionFact =
  (typeof COORDINATOR_SELECTION_FACTS)[number];
export type CoordinatorFallbackCode =
  (typeof COORDINATOR_FALLBACK_CODES)[number];

export interface CoordinatorExperiment {
  contract_version: "coordinator-experiment-v1";
  approach: "coordinator_assisted" | "deterministic_fallback";
  interpreted_preference_tags: InterpretedPreferenceTag[];
  selection_facts: CoordinatorSelectionFact[];
  fallback_code: CoordinatorFallbackCode | null;
}

export type CoordinatorPlanResponse =
  | (PlanningSuccess & { experiment: CoordinatorExperiment })
  | (PlanningFailure & { experiment: CoordinatorExperiment });

export type PlanningResponse = PlanResponse | CoordinatorPlanResponse;

export interface RequestErrorDetail {
  location: Array<string | number>;
  message: string;
}

export interface RequestValidationError {
  status: "error";
  error_code: "REQUEST_VALIDATION_ERROR";
  explanation: string;
  details: RequestErrorDetail[];
}
