import type {
  Money,
  NormalizedRequest,
  PlanResponse,
  RequestValidationError,
  TripPlanRequest,
  ValidationReport,
} from "./api-types";
import {
  PLANNING_FAILURE_CODES,
  SUPPORTED_CURRENCIES,
  SUPPORTED_INTERESTS,
  SUPPORTED_PACES,
  VIOLATION_CODES,
} from "./api-types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export class ApiRequestError extends Error {
  constructor(
    readonly kind: "validation" | "unexpected",
    readonly validation?: RequestValidationError,
  ) {
    super(
      kind === "validation"
        ? "Request validation failed"
        : "Unexpected API error",
    );
    this.name = "ApiRequestError";
  }
}

function isValidationError(value: unknown): value is RequestValidationError {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RequestValidationError>;
  return (
    candidate.status === "error" &&
    candidate.error_code === "REQUEST_VALIDATION_ERROR" &&
    typeof candidate.explanation === "string" &&
    Array.isArray(candidate.details) &&
    candidate.details.every(
      (detail) =>
        isRecord(detail) &&
        Array.isArray(detail.location) &&
        detail.location.every(
          (part) => typeof part === "string" || Number.isInteger(part),
        ) &&
        typeof detail.message === "string",
    )
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isPublicLabel(value: unknown): value is string {
  return (
    typeof value === "string" && value.trim().length > 0 && value.length <= 200
  );
}

function isEnumValue<T extends string>(
  value: unknown,
  values: readonly T[],
): value is T {
  return typeof value === "string" && values.includes(value as T);
}

function isMoney(value: unknown): value is Money {
  return (
    isRecord(value) &&
    Number.isSafeInteger(value.amount_minor) &&
    (value.amount_minor as number) >= 0 &&
    isEnumValue(value.currency, SUPPORTED_CURRENCIES)
  );
}

function isTimeWindow(value: unknown): boolean {
  return isRecord(value) && isTimestamp(value.start) && isTimestamp(value.end);
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

function isTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isTimeZone(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

function isPricing(value: unknown): boolean {
  return (
    isRecord(value) &&
    (value.basis === "per_person" || value.basis === "per_group") &&
    isMoney(value.unit_price) &&
    (value.charged_travellers === null ||
      Number.isInteger(value.charged_travellers))
  );
}

function isNormalizedRequest(value: unknown): value is NormalizedRequest {
  return (
    isRecord(value) &&
    typeof value.origin === "string" &&
    typeof value.destination === "string" &&
    isIsoDate(value.start_date) &&
    isIsoDate(value.end_date) &&
    Number.isInteger(value.travellers) &&
    isMoney(value.budget) &&
    Array.isArray(value.interests) &&
    value.interests.every((item) => isEnumValue(item, SUPPORTED_INTERESTS)) &&
    isEnumValue(value.pace, SUPPORTED_PACES) &&
    typeof value.earliest_activity_time === "string" &&
    /^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$/.test(
      value.earliest_activity_time,
    ) &&
    (value.destination_timezone === null ||
      isTimeZone(value.destination_timezone))
  );
}

function isValidationReport(value: unknown): value is ValidationReport {
  return (
    isRecord(value) &&
    typeof value.is_valid === "boolean" &&
    Array.isArray(value.violations) &&
    value.violations.every(
      (violation) =>
        isRecord(violation) &&
        isEnumValue(violation.code, VIOLATION_CODES) &&
        typeof violation.message === "string" &&
        isStringArray(violation.affected_ids) &&
        violation.severity === "error",
    )
  );
}

function isResponseBase(value: Record<string, unknown>): boolean {
  return (
    isNormalizedRequest(value.request) &&
    isValidationReport(value.validation_report) &&
    isStringArray(value.assumptions) &&
    isStringArray(value.warnings) &&
    (value.fixture_snapshot_version === null ||
      typeof value.fixture_snapshot_version === "string") &&
    typeof value.planner_id === "string" &&
    isStringArray(value.disclosures) &&
    value.disclosures.length >= 2
  );
}

function isScheduledItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.item_id === "string" &&
    typeof value.title === "string" &&
    ["activity", "meal", "transport"].includes(value.kind as string) &&
    isTimeWindow(value.window) &&
    ((value.location_id === null && value.location_label === null) ||
      (typeof value.location_id === "string" &&
        isPublicLabel(value.location_label))) &&
    isMoney(value.estimated_cost) &&
    (value.source_record_id === null ||
      typeof value.source_record_id === "string") &&
    isPricing(value.pricing) &&
    (value.transport_role === null ||
      ["inbound", "outbound", "local"].includes(value.transport_role as string))
  );
}

function isAccommodationStay(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.stay_id === "string" &&
    typeof value.title === "string" &&
    isTimestamp(value.check_in) &&
    isTimestamp(value.check_out) &&
    Number.isInteger(value.number_of_nights) &&
    ((value.location_id === null && value.location_label === null) ||
      (typeof value.location_id === "string" &&
        isPublicLabel(value.location_label))) &&
    isMoney(value.estimated_cost) &&
    (value.source_record_id === null ||
      typeof value.source_record_id === "string") &&
    isPricing(value.pricing)
  );
}

function isProposedItinerary(value: unknown): boolean {
  return (
    isRecord(value) &&
    Array.isArray(value.scheduled_items) &&
    value.scheduled_items.every(isScheduledItem) &&
    Array.isArray(value.accommodation_stays) &&
    value.accommodation_stays.every(isAccommodationStay) &&
    Array.isArray(value.explicit_fees) &&
    value.explicit_fees.every(
      (fee) =>
        isRecord(fee) &&
        typeof fee.fee_id === "string" &&
        typeof fee.title === "string" &&
        isMoney(fee.cost),
    ) &&
    Array.isArray(value.non_blocking_markers) &&
    value.non_blocking_markers.every(
      (marker) =>
        isRecord(marker) &&
        typeof marker.marker_id === "string" &&
        typeof marker.title === "string" &&
        isTimeWindow(marker.window),
    )
  );
}

function isCostBreakdown(value: unknown): boolean {
  return (
    isRecord(value) &&
    isMoney(value.transport) &&
    isMoney(value.accommodation) &&
    isMoney(value.activity) &&
    isMoney(value.meal) &&
    isMoney(value.fees_taxes) &&
    isMoney(value.total_estimated_cost)
  );
}

function isPlanResponse(value: unknown): value is PlanResponse {
  if (!isRecord(value) || !isResponseBase(value)) return false;
  const validationReport = value.validation_report;
  if (!isValidationReport(validationReport)) return false;
  if (value.status === "success") {
    return (
      validationReport.is_valid === true &&
      validationReport.violations.length === 0 &&
      typeof value.fixture_snapshot_version === "string" &&
      isProposedItinerary(value.proposed_itinerary) &&
      isCostBreakdown(value.cost_breakdown) &&
      Array.isArray(value.matched_interests) &&
      value.matched_interests.every((item) =>
        isEnumValue(item, SUPPORTED_INTERESTS),
      ) &&
      isStringArray(value.planning_rationale) &&
      value.planning_rationale.length > 0
    );
  }
  return (
    value.status === "planning_failure" &&
    validationReport.is_valid === false &&
    isEnumValue(value.failure_code, PLANNING_FAILURE_CODES) &&
    typeof value.explanation === "string" &&
    isStringArray(value.relevant_constraints)
  );
}

export async function createPlan(
  request: TripPlanRequest,
  signal?: AbortSignal,
): Promise<PlanResponse> {
  const baseUrl = (
    process.env.NEXT_PUBLIC_TRIPPILOT_API_BASE_URL || DEFAULT_API_BASE_URL
  ).replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/itineraries/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch {
    throw new ApiRequestError("unexpected");
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiRequestError("unexpected");
  }

  if (response.status === 422 && isValidationError(payload)) {
    throw new ApiRequestError("validation", payload);
  }
  if (!response.ok || !isPlanResponse(payload)) {
    throw new ApiRequestError("unexpected");
  }
  return payload;
}
