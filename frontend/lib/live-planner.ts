import type { TripPlanRequest } from "./api-types";
import { ApiRequestError, isValidationError } from "./api-client";
import {
  COST_LABELS,
  type CostCategory,
  type EnteredCosts,
  type LiveInputs,
} from "./live-inputs";

export type BudgetEstimate = {
  basis: "user_entered_all_travellers_whole_trip";
  currency: "CAD" | "USD";
  budget_minor: number;
  categories: EnteredCosts;
  status: "incomplete" | "within_entered_estimate" | "over_entered_estimate";
  known_subtotal_minor: number;
  estimated_total_minor: number | null;
  remaining_minor: number | null;
  missing_categories: CostCategory[];
};
export type TravelWindow = {
  basis: "user_entered";
  arrival: string;
  departure: string;
  available_from: string;
  available_until: string;
  transfer_buffer_minutes: number;
};

export type LiveDraft = {
  status:
    | "draft"
    | "unavailable"
    | "ambiguous_destination"
    | "no_places"
    | "invalid_window"
    | "budget_exceeded";
  city: {
    place_id: string;
    name: string;
    timezone: string;
    lat: number;
    lon: number;
  } | null;
  destination_choices: string[];
  stops: {
    place: {
      place_id: string;
      name: string;
      address: string;
      category: string;
      lat: number;
      lon: number;
    };
    day: string;
    start: string;
    end: string;
    walking_minutes_from_previous: number | null;
    visit_duration_basis: "estimated_60_minutes";
    opening_hours_status: "unverified";
    price_minor: null;
  }[];
  retrieved_at: string | null;
  budget_status: "not_verified";
  all_in_total_minor: null;
  budget_estimate: BudgetEstimate | null;
  travel_window: TravelWindow | null;
  notice: string;
  missing: string[];
  attribution: "Geoapify · © OpenStreetMap contributors (ODbL)";
};

function record(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function label(v: unknown): v is string {
  return typeof v === "string" && v.length > 0 && v.length <= 600;
}
function point(v: Record<string, unknown>) {
  return (
    typeof v.lat === "number" &&
    Number.isFinite(v.lat) &&
    Math.abs(v.lat) <= 90 &&
    typeof v.lon === "number" &&
    Number.isFinite(v.lon) &&
    Math.abs(v.lon) <= 180
  );
}
function timestamp(v: unknown): v is string {
  return (
    typeof v === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
    Number.isFinite(Date.parse(v))
  );
}
function keys(v: Record<string, unknown>, names: string) {
  const allowed = names.split(" ");
  return (
    Object.keys(v).length === allowed.length &&
    Object.keys(v).every((k) => allowed.includes(k))
  );
}

function isBudgetEstimate(v: unknown): v is BudgetEstimate {
  if (
    !record(v) ||
    !keys(
      v,
      "basis currency budget_minor categories status known_subtotal_minor estimated_total_minor remaining_minor missing_categories",
    ) ||
    v.basis !== "user_entered_all_travellers_whole_trip" ||
    !["CAD", "USD"].includes(String(v.currency)) ||
    !Number.isSafeInteger(v.budget_minor) ||
    Number(v.budget_minor) <= 0 ||
    Number(v.budget_minor) > 1e12 ||
    !record(v.categories) ||
    !keys(v.categories, Object.keys(COST_LABELS).join(" ")) ||
    !Array.isArray(v.missing_categories)
  )
    return false;
  let subtotal = 0;
  const missing: string[] = [];
  for (const category of Object.keys(COST_LABELS)) {
    const value = v.categories[category];
    if (value === null) missing.push(category);
    else if (
      !Number.isSafeInteger(value) ||
      Number(value) < 0 ||
      Number(value) > 1e12
    )
      return false;
    else subtotal += Number(value);
  }
  const total = missing.length ? null : subtotal;
  return (
    v.known_subtotal_minor === subtotal &&
    v.estimated_total_minor === total &&
    v.remaining_minor ===
      (total === null ? null : Number(v.budget_minor) - total) &&
    JSON.stringify(v.missing_categories) === JSON.stringify(missing) &&
    v.status ===
      (subtotal > Number(v.budget_minor)
        ? "over_entered_estimate"
        : missing.length
          ? "incomplete"
          : "within_entered_estimate")
  );
}
function isTravelWindow(v: unknown): v is TravelWindow {
  return (
    record(v) &&
    keys(
      v,
      "basis arrival departure available_from available_until transfer_buffer_minutes",
    ) &&
    v.basis === "user_entered" &&
    timestamp(v.arrival) &&
    timestamp(v.departure) &&
    timestamp(v.available_from) &&
    timestamp(v.available_until) &&
    Number.isInteger(v.transfer_buffer_minutes) &&
    Number(v.transfer_buffer_minutes) >= 0 &&
    Number(v.transfer_buffer_minutes) <= 240 &&
    Date.parse(v.available_from) ===
      Date.parse(v.arrival) + Number(v.transfer_buffer_minutes) * 60000 &&
    Date.parse(v.available_until) ===
      Date.parse(v.departure) - Number(v.transfer_buffer_minutes) * 60000 &&
    Date.parse(v.available_from) < Date.parse(v.available_until)
  );
}
export function isLiveDraft(v: unknown): v is LiveDraft {
  if (
    !record(v) ||
    !keys(
      v,
      "status city destination_choices stops retrieved_at budget_status all_in_total_minor budget_estimate travel_window notice missing attribution",
    ) ||
    ![
      "draft",
      "unavailable",
      "ambiguous_destination",
      "no_places",
      "invalid_window",
      "budget_exceeded",
    ].includes(String(v.status)) ||
    v.budget_status !== "not_verified" ||
    v.all_in_total_minor !== null ||
    !(v.budget_estimate === null || isBudgetEstimate(v.budget_estimate)) ||
    !(v.travel_window === null || isTravelWindow(v.travel_window)) ||
    typeof v.notice !== "string" ||
    v.notice.length > 2000 ||
    v.attribution !== "Geoapify · © OpenStreetMap contributors (ODbL)" ||
    !Array.isArray(v.destination_choices) ||
    v.destination_choices.length > 5 ||
    !v.destination_choices.every(label) ||
    !Array.isArray(v.missing) ||
    !v.missing.every(label) ||
    !Array.isArray(v.stops) ||
    v.stops.length > 8 ||
    !(v.retrieved_at === null || timestamp(v.retrieved_at))
  )
    return false;
  if (v.city !== null) {
    if (
      !record(v.city) ||
      !keys(v.city, "place_id name timezone lat lon") ||
      !label(v.city.place_id) ||
      !label(v.city.name) ||
      !point(v.city) ||
      typeof v.city.timezone !== "string"
    )
      return false;
    try {
      new Intl.DateTimeFormat("en", { timeZone: v.city.timezone });
    } catch {
      return false;
    }
  }
  const ids = new Set<string>();
  for (const s of v.stops) {
    if (
      !record(s) ||
      !keys(
        s,
        "place day start end walking_minutes_from_previous visit_duration_basis opening_hours_status price_minor",
      ) ||
      !record(s.place) ||
      !keys(s.place, "place_id name address category lat lon") ||
      !label(s.place.place_id) ||
      ids.has(s.place.place_id) ||
      !label(s.place.name) ||
      typeof s.place.address !== "string" ||
      !label(s.place.category) ||
      !point(s.place) ||
      typeof s.day !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(s.day) ||
      !timestamp(s.start) ||
      !timestamp(s.end) ||
      Date.parse(s.end) <= Date.parse(s.start) ||
      !(
        s.walking_minutes_from_previous === null ||
        (Number.isInteger(s.walking_minutes_from_previous) &&
          Number(s.walking_minutes_from_previous) >= 1 &&
          Number(s.walking_minutes_from_previous) <= 45)
      ) ||
      s.visit_duration_basis !== "estimated_60_minutes" ||
      s.opening_hours_status !== "unverified" ||
      s.price_minor !== null
    )
      return false;
    ids.add(s.place.place_id);
    if (
      v.travel_window !== null &&
      isTravelWindow(v.travel_window) &&
      (Date.parse(s.start) < Date.parse(v.travel_window.available_from) ||
        Date.parse(s.end) > Date.parse(v.travel_window.available_until))
    )
      return false;
  }
  if (
    v.status === "budget_exceeded" &&
    (!isBudgetEstimate(v.budget_estimate) ||
      v.budget_estimate.status !== "over_entered_estimate")
  )
    return false;
  if (
    v.status === "draft" &&
    isBudgetEstimate(v.budget_estimate) &&
    v.budget_estimate.status === "over_entered_estimate"
  )
    return false;
  return v.status === "draft"
    ? v.city !== null && v.retrieved_at !== null && v.stops.length > 0
    : v.stops.length === 0;
}

export async function createLivePlan(
  request: TripPlanRequest & Partial<LiveInputs>,
): Promise<LiveDraft> {
  const base =
    process.env.NEXT_PUBLIC_TRIPPILOT_API_BASE_URL || "http://127.0.0.1:8000";
  const response = await fetch(`${base}/api/v1/itineraries/live-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(12000),
  });
  const value: unknown = await response.json();
  if (response.status === 422 && isValidationError(value))
    throw new ApiRequestError("validation", value);
  if (!response.ok) throw new Error("Live planning unavailable");
  if (!isLiveDraft(value)) throw new Error("Invalid live draft");
  return value;
}
