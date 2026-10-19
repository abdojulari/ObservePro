import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { buildQuery, rangeDurationMs, severityClass } from "../lib/utils";
import { getProjectId } from "../api/client";
import { installApi, renderAt } from "./render";

describe("dashboard helpers", () => {
  it("maps severity colors and range windows", () => {
    expect(severityClass("INFO")).toContain("sky");
    expect(severityClass("WARN")).toContain("amber");
    expect(severityClass("ERROR")).toContain("red");
    expect(severityClass("FATAL")).toContain("red-700");
    expect(rangeDurationMs("15m")).toBe(15 * 60 * 1000);
    expect(buildQuery({ q: "payment", severity: "", page: 1 })).toBe("?q=payment&page=1");
  });
});

describe("dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    installApi();
  });

  it("renders overview numbers from the API", async () => {
    renderAt("/");
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getAllByText("Log volume").length).toBeGreaterThan(0);
  });

  it("shows an error state when overview fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/projects")) {
        return new Response(JSON.stringify([{ id: "project-1", name: "Payments", slug: "payments", created_at: "2026-10-19T12:00:00Z" }]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "overview unavailable" }), { status: 500 });
    }));
    renderAt("/");
    expect(await screen.findByText("overview unavailable")).toBeInTheDocument();
  });

  it("searches logs and opens the linked trace", async () => {
    const user = userEvent.setup();
    const calls = installApi();
    renderAt("/logs");
    expect(await screen.findByText("Payment processing failed")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search logs"), "payment");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls.some((call) => call.path.includes("q=payment"))).toBe(true));
    await user.click(screen.getByRole("link", { name: "abc123" }));
    expect((await screen.findAllByRole("heading", { name: "POST /pay" })).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Back to traces" })).toBeInTheDocument();
  });

  it("acknowledges an alert", async () => {
    const user = userEvent.setup();
    const calls = installApi();
    renderAt("/alerts");
    await user.click(await screen.findByRole("button", { name: /Payment failure rate/ }));
    await user.click(await screen.findByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.path.endsWith("/acknowledge"))).toBe(true));
  });

  it("changes the time range used by overview", async () => {
    const user = userEvent.setup();
    const calls = installApi();
    renderAt("/");
    await screen.findByText("12");
    await user.click(screen.getByRole("button", { name: "15m" }));
    await waitFor(() => expect(calls.some((call) => call.path.includes("range=15m"))).toBe(true));
  });

  it("switches the active project", async () => {
    const user = userEvent.setup();
    renderAt("/");
    await screen.findByText("12");
    await user.selectOptions(screen.getByLabelText("Project"), "project-2");
    expect(getProjectId()).toBe("project-2");
  });
});
