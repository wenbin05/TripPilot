import type { TripPlanRequest } from "./api-types";

export type LiveDraft = {
  status: "draft" | "unavailable" | "ambiguous_destination" | "no_places";
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
export function isLiveDraft(v: unknown): v is LiveDraft {
  if (
    !record(v) ||
    !keys(
      v,
      "status city destination_choices stops retrieved_at budget_status all_in_total_minor notice missing attribution",
    ) ||
    !["draft", "unavailable", "ambiguous_destination", "no_places"].includes(
      String(v.status),
    ) ||
    v.budget_status !== "not_verified" ||
    v.all_in_total_minor !== null ||
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
  }
  return v.status === "draft"
    ? v.city !== null && v.retrieved_at !== null && v.stops.length > 0
    : v.stops.length === 0;
}

export async function createLivePlan(
  request: TripPlanRequest,
): Promise<LiveDraft> {
  const base =
    process.env.NEXT_PUBLIC_TRIPPILOT_API_BASE_URL || "http://127.0.0.1:8000";
  const response = await fetch(`${base}/api/v1/itineraries/live-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error("Live planning unavailable");
  const value: unknown = await response.json();
  if (!isLiveDraft(value)) throw new Error("Invalid live draft");
  return value;
}
