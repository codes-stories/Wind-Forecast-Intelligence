import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type {
  AccuracyResponse,
  DataQualityResponse,
  HealthResponse,
  InsightsResponse,
  TimeseriesResponse,
  VintageIntervalResponse,
} from "./api/types";

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
  median_abs_error_mw: 1400,
  p90_abs_error_mw: 4800,
  n_missing_actual: 6,
  n_missing_forecast: 8,
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

const vintages: VintageIntervalResponse = {
  delivery_timestamp: "2026-01-15T12:00:00Z",
  settlement_date: "2026-01-15",
  settlement_period: 25,
  clock_hour: "2026-01-15T12:00:00Z",
  cutoff_utc: "2026-01-14T09:20:00Z",
  actual_mw: 12000,
  selected_publish_time: "2026-01-14T07:30:00Z",
  selected_forecast_mw: 11500,
  error_mw: -500,
  absolute_error_mw: 500,
  latest_publish_time: "2026-01-14T09:30:00Z",
  latest_forecast_mw: 11800,
  eligible_count: 1,
  post_cutoff_count: 1,
  vintages: [
    {
      publish_time: "2026-01-14T07:30:00Z",
      forecast_mw: 11500,
      change_mw: null,
      eligible_at_cutoff: true,
      selected: true,
    },
    {
      publish_time: "2026-01-14T09:30:00Z",
      forecast_mw: 11800,
      change_mw: 300,
      eligible_at_cutoff: false,
      selected: false,
    },
  ],
  limitation: null,
  note: "Eligible means publishTime <= cutoff; latest may be post-cutoff.",
};

const dataQuality: DataQualityResponse = {
  sources: { actual: "Elexon FUELHH (wind, half-hourly)", forecast: "Elexon WINDFOR (hourly vintage)" },
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  decision_cutoff_utc: "09:20",
  expected_halfhourly_intervals: 1488,
  actual_records_fetched: 1488,
  actual_records_present: 1488,
  forecast_records_fetched: 1488,
  eligible_forecast_records: 744,
  selected_forecast_records: 744,
  matched_intervals: 1488,
  missing_actual_intervals: 0,
  missing_forecast_intervals: 0,
  coverage_pct: 100,
  duplicate_records_dropped: { actual: 0, forecast: 0 },
  null_values_in_source: { actual: 0, forecast: 0 },
  cache_loaded_at: "2026-01-31T12:00:00Z",
  cache_age_seconds: 10,
  cache_ttl_seconds: 3600,
  quality_status: "complete",
  limitations: ["WINDFOR generation is assumed to be MW; the unit is not documented by Elexon."],
  note: "Counts are computed from the dataset currently served by this API.",
};

const insights: InsightsResponse = {
  grain: "halfhourly",
  start: "2026-01-01",
  end: "2026-01-31",
  insights: [
    {
      id: "bias_direction",
      finding: "Forecast generation was on average 250.0 MW too high (over-forecast).",
      evidence: "Mean signed error (forecast - actual) = +250.0 MW over 730 matched intervals.",
      period: "2026-01-01 to 2026-01-31 (UTC delivery dates)",
      why_it_matters: "Persistent bias indicates which way the forecast tends to err.",
      available: true,
      unavailable_reason: null,
    },
    {
      id: "coverage",
      finding: "730 of 744 expected intervals were matched (98.1% coverage).",
      evidence: "Missing actual: 6. Missing forecast: 8.",
      period: "2026-01-01 to 2026-01-31 (UTC delivery dates)",
      why_it_matters: "Coverage states how much of the range the statistics rest on.",
      available: true,
      unavailable_reason: null,
    },
  ],
  note: "Every insight lists the numbers behind it (evidence).",
};

const fetchMock = vi.fn();

function mockApi() {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/health")) return jsonResponse(health);
    if (url.includes("/api/accuracy")) return jsonResponse(accuracy);
    if (url.includes("/api/timeseries")) return jsonResponse(timeseries);
    if (url.includes("/api/forecasts/vintages")) return jsonResponse(vintages);
    if (url.includes("/api/data-quality")) return jsonResponse(dataQuality);
    if (url.includes("/api/insights")) return jsonResponse(insights);
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

describe("Section navigation and new features", () => {
  it("renders the four analysis sections as tabs", async () => {
    render(<App />);
    await screen.findByText("13,000 MW");
    for (const name of ["Overview", "Forecast Explorer", "Error Analysis", "Data Quality"]) {
      expect(screen.getByRole("tab", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  it("renders evidence-based insights on the overview", async () => {
    render(<App />);
    expect(await screen.findByText(/on average 250\.0 MW too high \(over-forecast\)/)).toBeInTheDocument();
    expect(screen.getByText(/Mean signed error \(forecast - actual\)/)).toBeInTheDocument();
    expect(screen.getByText(/730 of 744 expected intervals were matched/)).toBeInTheDocument();
  });

  it("opens the Forecast Explorer with selected vs post-cutoff vintages", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("13,000 MW");
    fetchMock.mockClear();
    await user.click(screen.getByRole("tab", { name: "Forecast Explorer" }));

    expect(await screen.findByText("selected (at cutoff)")).toBeInTheDocument();
    expect(screen.getByText("post-cutoff, excluded")).toBeInTheDocument();
    // selected vintage drives the displayed error (F - A)
    expect(screen.getByText("-500.0 MW")).toBeInTheDocument();
    // selected and latest must stay distinct (stat card + history table each)
    expect(screen.getAllByText("11,500 MW").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("11,800 MW").length).toBeGreaterThanOrEqual(2);
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/forecasts/vintages") && u.includes("period=25"))).toBe(true);
    // overview content is not rendered on this tab
    expect(screen.queryByText("13,000 MW")).not.toBeInTheDocument();
  });

  it("shows the heatmap and reliability indicators on Error Analysis", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("13,000 MW");
    await user.click(screen.getByRole("tab", { name: "Error Analysis" }));

    expect(await screen.findByText("Forecast error heatmap")).toBeInTheDocument();
    expect(screen.getByText("Reliability & risk indicators")).toBeInTheDocument();
    expect(screen.getByText("1,400 MW")).toBeInTheDocument(); // median |error| from accuracy
    expect(screen.getByText("4,800 MW")).toBeInTheDocument(); // p90 |error| from accuracy
    // heatmap toggle controls exist and toggle aria-pressed
    const signed = screen.getByRole("button", { name: "Signed error" });
    expect(signed).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Absolute error" }));
    expect(screen.getByRole("button", { name: "Absolute error" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows provenance and limitations on Data Quality", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("13,000 MW");
    fetchMock.mockClear();
    await user.click(screen.getByRole("tab", { name: "Data Quality" }));

    expect(await screen.findByText("Dataset status")).toBeInTheDocument();
    expect(screen.getByText("all intervals matched")).toBeInTheDocument();
    expect(screen.getAllByText("1488").length).toBeGreaterThanOrEqual(1); // expected/matched
    expect(screen.getByText("Eligible forecast records")).toBeInTheDocument();
    expect(screen.getByText(/assumed to be MW/)).toBeInTheDocument(); // limitations list
    expect(screen.queryByRole("link", { name: "Export CSV" })).not.toBeInTheDocument(); // no FilterBar here
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/data-quality"))).toBe(true);
  });

  it("offers a CSV export link reflecting the current filters", async () => {
    render(<App />);
    await screen.findByText("13,000 MW");
    const link = screen.getByRole("link", { name: "Export CSV" });
    expect(link.getAttribute("href")).toContain(
      "/api/export.csv?start=2026-01-01&end=2026-01-31&grain=halfhourly",
    );
    fireEvent.change(screen.getByLabelText("Aggregation"), { target: { value: "daily" } });
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Export CSV" }).getAttribute("href")).toContain(
        "/api/export.csv?start=2026-01-01&end=2026-01-31&grain=hourly",
      );
    });
  });
});
