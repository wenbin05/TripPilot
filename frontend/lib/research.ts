export type ResearchResponse = {
  status: "evidence" | "generated" | "no_evidence" | "unavailable";
  passages: {
    id: string;
    text: string;
    source_title: string;
    source_url: string;
    retrieved_at: string;
    revision: number;
  }[];
  claims: { text: string; citations: string[] }[];
  notice: string;
  generation_note:
    | "not_requested"
    | "not_configured"
    | "completed"
    | "failed"
    | "no_evidence";
  attribution: string;
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isResearchResponse(value: unknown): value is ResearchResponse {
  if (
    !record(value) ||
    !["evidence", "generated", "no_evidence", "unavailable"].includes(
      String(value.status),
    ) ||
    ![
      "not_requested",
      "not_configured",
      "completed",
      "failed",
      "no_evidence",
    ].includes(String(value.generation_note)) ||
    typeof value.notice !== "string" ||
    typeof value.attribution !== "string" ||
    !Array.isArray(value.passages) ||
    value.passages.length > 4 ||
    !Array.isArray(value.claims) ||
    value.claims.length > 4
  )
    return false;
  const ids = new Set<string>();
  for (const p of value.passages) {
    if (
      !record(p) ||
      typeof p.id !== "string" ||
      !/^p\d+$/.test(p.id) ||
      ids.has(p.id) ||
      typeof p.text !== "string" ||
      p.text.length > 2500 ||
      typeof p.source_title !== "string" ||
      typeof p.source_url !== "string" ||
      !/^https:\/\/en\.wikivoyage\.org\/w\/index\.php\?oldid=\d+$/.test(
        p.source_url,
      ) ||
      typeof p.retrieved_at !== "string" ||
      !Number.isFinite(Date.parse(p.retrieved_at)) ||
      !Number.isSafeInteger(p.revision) ||
      Number(p.revision) <= 0
    )
      return false;
    ids.add(p.id);
  }
  return value.claims.every(
    (c) =>
      record(c) &&
      typeof c.text === "string" &&
      c.text.length <= 800 &&
      Array.isArray(c.citations) &&
      c.citations.length > 0 &&
      c.citations.length <= 4 &&
      c.citations.every((id) => typeof id === "string" && ids.has(id)),
  );
}

export async function researchDestination(
  destination: string,
  question: string,
  synthesize: boolean,
): Promise<ResearchResponse> {
  const base =
    process.env.NEXT_PUBLIC_TRIPPILOT_API_BASE_URL || "http://127.0.0.1:8000";
  const response = await fetch(`${base}/api/v1/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destination, question, synthesize }),
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error("Research request failed");
  const value: unknown = await response.json();
  if (!isResearchResponse(value)) throw new Error("Invalid research response");
  return value;
}
