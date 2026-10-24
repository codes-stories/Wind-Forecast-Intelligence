import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { AccuracyResponse, HealthResponse, TimeseriesResponse } from "./api/types";

const health: HealthResponse = {
  status: "ok",
  service: "uk-wind-forecast-intelligence-api",
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  decision_cutoff_utc: "09:20",
  cache: {
    loaded: true,
    loaded_at: "2026-01-31T12:00:00Z",
    age_seconds: 10,
    ttl_seconds: 3600,
    refresh: "lazy",
    endpoint_refresh_param: "?refresh=true",
  },
};

const accuracy: AccuracyResponse = {
  grain: "halfhourly",
  n_expected: 744,
  n_matched: 730,
  n_missing: 14,
  coverage_pct: 98.12,
  coverage_complete: false,
  mae_mw: 1500,
  rmse_mw: 2500,
  bias_mw: 250,
  mape_pct: 12.5,
  mape_excluded_intervals: 0,
  avg_forecast_mw: 13000,
  avg_actual_mw: 12750,
  status_counts: { matched: 730, forecast_only: 6, actual_only: 8, missing_both: 0 },
  start: "2026-01-01",
  end: "2026-01-31",
  note: "Metrics computed over matched intervals only.",
};

const timeseries: TimeseriesResponse = {
  grain: "halfhourly",
  start: "2026-01-01",
  end: "2026-01-31",
  rows: [
    {
      timestamp: "2026-01-01T00:00:00Z",
      settlement_date: "2026-01-01",
      settlement_period: 1,
      actual_mw: 10000,
      forecast_mw: 11000,
      error_mw: 1000,
      status: "matched",
      forecast_publish_time: "2025-12-31T07:30:00Z",
    },
    {
      timestamp: "2026-01-01T00:30:00Z",
      settlement_date: "2026-01-01",
      settlement_period: 2,
      actual_mw: 10200,
      forecast_mw: 11000,
      error_mw: 800,
      status: "matched",
      forecast_publish_time: "2025-12-31T07:30:00Z",
    },
    {
      timestamp: "2026-01-02T00:00:00Z",
      settlement_date: "2026-01-02",
      settlement_period: 1,
      actual_mw: null,
      forecast_mw: 9000,
      error_mw: null,
      status: "forecast_only",
      forecast_publish_time: "2026-01-01T07:30:00Z",
    },
  ],
};

function jsonResponse(data: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }),
  );
}

const fetchMock = vi.fn();

function mockApi() {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/health")) return jsonResponse(health);
    if (url.includes("/api/accuracy")) return jsonResponse(accuracy);
    if (url.includes("/api/timeseries")) return jsonResponse(timeseries);
    return jsonResponse({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  mockApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App loading state", () => {
  it("shows a loading indicator while requests are in flight", () => {
    fetchMock.mockImplementation(() => new Promise<Response>(() => undefined)); // never resolves
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading analysis");
  });
});

describe("App error state", () => {
  it("shows a retryable error panel when the backend is unreachable", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("network down")));
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Backend unreachable");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("surfaces backend HTTP error details", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/health")) return jsonResponse(health);
      return jsonResponse({ detail: "start must be on or before end" }, 400);
    });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("start must be on or before end");
  });
});

describe("App rendering API-derived values", () => {
  it("renders KPI values from the accuracy response", async () => {
    render(<App />);
    expect(await screen.findByText("13,000 MW")).toBeInTheDocument(); // avg forecast
    expect(screen.getByText("12,750 MW")).toBeInTheDocument(); // avg actual
    expect(screen.getByText("1,500 MW")).toBeInTheDocument(); // MAE
    expect(screen.getByText("2,500 MW")).toBeInTheDocument(); // RMSE
    expect(screen.getByText("+250.0 MW")).toBeInTheDocument(); // bias (over-forecast)
    expect(screen.getByText("98.1%")).toBeInTheDocument(); // coverage
    expect(screen.getByText(/730 of 744 intervals matched/)).toBeInTheDocument();
  });

  it("renders header with period, Elexon attribution and decision cutoff", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Wind Forecast Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/Reporting period: 2026-01-01 — 2026-01-31/)).toBeInTheDocument();
    expect(screen.getByText("Elexon BMRS")).toBeInTheDocument();
    expect(screen.getByText(/Decision cutoff: 09:20 UTC on D-1/)).toBeInTheDocument();
  });

  it("renders table rows with publication timestamps and availability status", async () => {
    render(<App />);
    expect(await screen.findByText("01 Jan 00:00 UTC")).toBeInTheDocument();
    // rows 1 and 2 share the same selected 07:30 vintage
    expect(screen.getAllByText("31 Dec 07:30 UTC")).toHaveLength(2);
    expect(screen.getByText("forecast only")).toBeInTheDocument(); // status badge
    // missing values are shown as em dash, never 0 MW
    const missingRow = screen.getByText("forecast only").closest("tr");
    expect(missingRow).toHaveTextContent("—");
  });
});

describe("Filters", () => {
  it("requests hourly accuracy metrics when daily aggregation is selected", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("13,000 MW");
    fetchMock.mockClear();
    await user.selectOptions(screen.getByLabelText("Aggregation"), "daily");
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("/api/accuracy") && u.includes("grain=hourly"))).toBe(true);
      // timeseries stays at the native half-hourly grain (daily derived client-side)
      expect(urls.some((u) => u.includes("/api/timeseries") && u.includes("grain=halfhourly"))).toBe(true);
    });
    // daily table: one aggregated row per delivery day
    expect(await screen.findByText("01 Jan")).toBeInTheDocument();
    expect(screen.getByText("02 Jan")).toBeInTheDocument();
  });

  it("passes the selected date range to the backend", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("13,000 MW");
    fetchMock.mockClear();
    fireEvent.change(screen.getByLabelText("From (delivery date)"), { target: { value: "2026-01-10" } });
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("start=2026-01-10"))).toBe(true);
    });
    await user.click(screen.getByRole("button", { name: "Reset to January 2026" }));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("start=2026-01-01") && u.includes("end=2026-01-31"))).toBe(true);
    });
  });

  it("warns instead of fetching when the range is inverted", async () => {
    render(<App />);
    await screen.findByText("13,000 MW");
    fetchMock.mockClear();
    // end before start is still a valid range -> one fetch
    fireEvent.change(screen.getByLabelText("To (delivery date)"), { target: { value: "2026-01-05" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const callsBefore = fetchMock.mock.calls.length;
    // now invert the range -> warning shown, no further requests
    fireEvent.change(screen.getByLabelText("From (delivery date)"), { target: { value: "2026-01-20" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Start date must be on or before end date.",
    );
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });
});
