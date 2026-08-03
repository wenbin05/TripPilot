import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TripPlanner } from "@/components/TripPlanner";
import { ApiRequestError, createPlan } from "@/lib/api-client";
import { SUPPORTED_INTERESTS, type PlanResponse } from "@/lib/api-types";
import { humanize } from "@/lib/format";
import { failureResponse, successResponse } from "./fixtures";

vi.mock("@/lib/api-client", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api-client")>(
      "@/lib/api-client",
    );
  return { ...actual, createPlan: vi.fn() };
});

const mockedCreatePlan = vi.mocked(createPlan);

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Origin"), "Kingston, Ontario");
  await user.type(
    screen.getByLabelText("Destination city"),
    "Toronto, Ontario",
  );
  await user.type(screen.getByLabelText("Start date"), "2026-08-10");
  await user.type(screen.getByLabelText("End date"), "2026-08-11");
  await user.type(screen.getByLabelText("Total budget"), "1000.00");
  await user.click(screen.getByLabelText("Arts Culture"));
}

async function submitValid(response: PlanResponse = successResponse) {
  const user = userEvent.setup();
  mockedCreatePlan.mockResolvedValueOnce(response);
  await fillValidForm(user);
  await user.click(
    screen.getByRole("button", { name: "Create proposed itinerary" }),
  );
  return user;
}

beforeEach(() => {
  mockedCreatePlan.mockReset();
});

describe("TripPlanner form", () => {
  it("renders every required trip and constraint field", () => {
    render(<TripPlanner />);
    for (const label of [
      "Origin",
      "Destination city",
      "Start date",
      "End date",
      "Number of travellers",
      "Total budget",
      "Currency",
      "Earliest acceptable activity time",
    ])
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Travel pace" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Trip interests" }),
    ).toBeInTheDocument();
  });

  it("renders exactly the supported API interest values", () => {
    render(<TripPlanner />);
    for (const interest of SUPPORTED_INTERESTS) {
      expect(screen.getByLabelText(humanize(interest))).toBeInTheDocument();
    }
  });

  it("reports missing fields in an accessible summary", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveFocus();
    expect(within(alert).getByText("Enter an origin.")).toBeInTheDocument();
    expect(screen.getByLabelText("Origin")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("catches identical origin and destination", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    await user.type(screen.getByLabelText("Origin"), "Toronto");
    await user.type(screen.getByLabelText("Destination city"), "toronto");
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(
      screen.getAllByText("Origin and destination must differ.").length,
    ).toBeGreaterThan(0);
  });

  it("catches a trip longer than four inclusive days", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    await user.type(screen.getByLabelText("Start date"), "2026-08-10");
    await user.type(screen.getByLabelText("End date"), "2026-08-14");
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(
      screen.getAllByText(
        "Trip length must be between one and four inclusive days.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("catches a non-positive budget", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    await user.type(screen.getByLabelText("Total budget"), "0");
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(
      screen.getAllByText("Enter a positive budget.").length,
    ).toBeGreaterThan(0);
  });

  it("requires at least one interest", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(
      screen.getAllByText("Select at least one interest.").length,
    ).toBeGreaterThan(0);
  });

  it("sends a valid payload matching the public API contract", async () => {
    render(<TripPlanner />);
    await submitValid();
    expect(mockedCreatePlan).toHaveBeenCalledWith({
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
    });
  });

  it("supports keyboard toggling for interests", async () => {
    const user = userEvent.setup();
    render(<TripPlanner />);
    const food = screen.getByLabelText("Food");
    food.focus();
    await user.keyboard(" ");
    expect(food).toBeChecked();
    await user.keyboard(" ");
    expect(food).not.toBeChecked();
  });
});

describe("TripPlanner submission states", () => {
  it("shows a loading state while the API request is pending", async () => {
    let resolvePlan!: (value: typeof successResponse) => void;
    mockedCreatePlan.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePlan = resolve;
        }),
    );
    const user = userEvent.setup();
    render(<TripPlanner />);
    await fillValidForm(user);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Creating your proposal",
    );
    resolvePlan(successResponse);
    await screen.findByText("Constraints validated");
  });

  it("displays a successful proposed itinerary", async () => {
    const responseWithPartiallyMatchedInterests: PlanResponse = {
      ...successResponse,
      request: {
        ...successResponse.request,
        interests: ["arts_culture", "history"],
      },
      matched_interests: ["arts_culture"],
    };
    render(<TripPlanner />);
    await submitValid(responseWithPartiallyMatchedInterests);
    expect(
      await screen.findByText("Constraints validated"),
    ).toBeInTheDocument();
    expect(screen.getByText("Day-by-day plan")).toBeInTheDocument();
    expect(screen.getByText("Harbour walk")).toBeInTheDocument();
    const matchedInterests = screen.getByRole("heading", {
      name: "Matched interests",
    });
    const matchedSection = matchedInterests.closest("section");
    expect(matchedSection).toHaveTextContent("Arts Culture");
    expect(matchedSection).not.toHaveTextContent("History");
    expect(
      screen
        .getByRole("heading", { name: "Your constraints" })
        .closest("section"),
    ).toHaveTextContent("Arts Culture, History");
  });

  it("sorts scheduled items chronologically in day cards", async () => {
    render(<TripPlanner />);
    await submitValid();
    await screen.findByText("Day-by-day plan");
    const titles = screen
      .getAllByRole("heading", { level: 4 })
      .map((heading) => heading.textContent);
    expect(titles.slice(0, 3)).toEqual([
      "Morning train",
      "Gallery visit",
      "Harbour walk",
    ]);
  });

  it("shows accommodation separately as non-time-blocking", async () => {
    render(<TripPlanner />);
    await submitValid();
    const accommodation = await screen.findByRole("heading", {
      name: "Accommodation",
    });
    const section = accommodation.closest("section");
    expect(section).toHaveTextContent("Campus guest house");
    expect(section).toHaveTextContent("does not block activity time");
    expect(
      screen.getByText("Day-by-day plan").closest("section"),
    ).not.toHaveTextContent("Campus guest house");
  });

  it("renders category costs, total, and remaining budget", async () => {
    render(<TripPlanner />);
    await submitValid();
    const cost = (
      await screen.findByRole("heading", { name: "Cost breakdown" })
    ).closest("section");
    expect(cost).toHaveTextContent("Transport");
    expect(cost).toHaveTextContent("CAD 500.00");
    expect(cost).toHaveTextContent("Remaining budget");
  });

  it("keeps the mock-data and no-booking disclosure visible", () => {
    render(<TripPlanner />);
    const notice = screen.getByLabelText("Important estimate notice");
    expect(notice).toHaveTextContent("Mock data");
    expect(notice).toHaveTextContent("Nothing has been booked");
    expect(notice).toHaveTextContent("Verify before purchase");
  });

  it("shows structured planning failure without calling it a network error", async () => {
    render(<TripPlanner />);
    await submitValid(failureResponse);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Could not create a valid plan",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("budget 1000 CAD")).toBeInTheDocument();
    expect(screen.queryByText("Proposal unavailable")).not.toBeInTheDocument();
  });

  it("maps 422 field errors to controls and the accessible summary", async () => {
    mockedCreatePlan.mockRejectedValueOnce(
      new ApiRequestError("validation", {
        status: "error",
        error_code: "REQUEST_VALIDATION_ERROR",
        explanation: "raw backend explanation",
        details: [{ location: ["destination"], message: "raw field detail" }],
      }),
    );
    const user = userEvent.setup();
    render(<TripPlanner />);
    await fillValidForm(user);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveFocus();
    expect(alert).toHaveTextContent(
      "The backend rejected the destination city.",
    );
    expect(screen.getByLabelText("Destination city")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.queryByText("raw field detail")).not.toBeInTheDocument();
  });

  it("shows a safe generic message for unexpected failures", async () => {
    mockedCreatePlan.mockRejectedValueOnce(
      new Error("RuntimeError at /private/fixture.json"),
    );
    const user = userEvent.setup();
    render(<TripPlanner />);
    await fillValidForm(user);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    expect(
      await screen.findByText(
        "TripPilot could not create a proposal right now. Please try again.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/RuntimeError|\/private/),
    ).not.toBeInTheDocument();
  });

  it("retains user inputs after a planning failure", async () => {
    render(<TripPlanner />);
    await submitValid(failureResponse);
    await screen.findByRole("heading", {
      level: 1,
      name: "Could not create a valid plan",
    });
    expect(screen.getByLabelText("Origin")).toHaveValue("Kingston, Ontario");
    expect(screen.getByLabelText("Total budget")).toHaveValue("1000.00");
    expect(screen.getByLabelText("Arts Culture")).toBeChecked();
  });

  it("never exposes raw unexpected backend details", async () => {
    mockedCreatePlan.mockRejectedValueOnce(new ApiRequestError("unexpected"));
    const user = userEvent.setup();
    render(<TripPlanner />);
    await fillValidForm(user);
    await user.click(
      screen.getByRole("button", { name: "Create proposed itinerary" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Proposal unavailable",
      ),
    );
    expect(document.body.textContent).not.toMatch(
      /stack|traceback|python|fixture\.json/i,
    );
  });
});
