import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DestinationResearch } from "@/components/DestinationResearch";
import { isResearchResponse } from "@/lib/research";

const evidence = {
  status: "evidence",
  passages: [
    {
      id: "p0",
      text: "Museums surround the park.",
      source_title: "Test City",
      source_url: "https://en.wikivoyage.org/w/index.php?oldid=42",
      retrieved_at: "2026-09-24T12:00:00Z",
      revision: 42,
    },
  ],
  claims: [],
  notice: "External research. Nothing is booked.",
  generation_note: "not_requested",
  attribution: "Wikivoyage contributors · CC BY-SA 4.0",
};
afterEach(() => vi.unstubAllGlobals());

describe("research contract", () => {
  it("accepts cited evidence", () =>
    expect(isResearchResponse(evidence)).toBe(true));
  it("rejects unsafe URLs and invented citations", () => {
    expect(
      isResearchResponse({
        ...evidence,
        passages: [
          { ...evidence.passages[0], source_url: "javascript:alert(1)" },
        ],
      }),
    ).toBe(false);
    expect(
      isResearchResponse({
        ...evidence,
        claims: [{ text: "x", citations: ["fake"] }],
      }),
    ).toBe(false);
    expect(isResearchResponse({ ...evidence, generation_note: "secret" })).toBe(
      false,
    );
  });
});

describe("research UI", () => {
  it("submits opt-out by default and renders source evidence", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => evidence });
    vi.stubGlobal("fetch", fetchMock);
    render(<DestinationResearch />);
    fireEvent.change(screen.getByLabelText("Destination guide"), {
      target: { value: "Test City" },
    });
    fireEvent.change(screen.getByLabelText("What would you like to explore?"), {
      target: { value: "Museums" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Research destination" }),
    );
    expect(
      await screen.findByText("Museums surround the park."),
    ).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.synthesize).toBe(false);
    expect(
      screen.getByRole("link", { name: "Read cited revision ↗" }),
    ).toHaveAttribute("href", evidence.passages[0].source_url);
  });
  it("retains inputs and shows safe failure on malformed response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
    );
    render(<DestinationResearch />);
    fireEvent.change(screen.getByLabelText("Destination guide"), {
      target: { value: "Toronto" },
    });
    fireEvent.change(screen.getByLabelText("What would you like to explore?"), {
      target: { value: "parks" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Research destination" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "could not be loaded",
      ),
    );
    expect(screen.getByLabelText("Destination guide")).toHaveValue("Toronto");
  });
});
