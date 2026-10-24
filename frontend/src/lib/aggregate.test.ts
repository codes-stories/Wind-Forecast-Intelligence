import { describe, expect, it } from "vitest";
import type { TimeseriesRow } from "../api/types";
import {
  errorHistogram,
  formatMw,
  p90AbsError,
  toDailyPoints,
  toHalfhourlyPoints,
} from "./aggregate";

function row(overrides: Partial<TimeseriesRow>): TimeseriesRow {
  return {
    timestamp: "2026-01-01T00:00:00Z",
    settlement_date: "2026-01-01",
    settlement_period: 1,
    actual_mw: 10000,
    forecast_mw: 11000,
    error_mw: 1000,
    status: "matched",
    forecast_publish_time: "2025-12-31T07:30:00Z",
    ...overrides,
  };
}

describe("formatMw", () => {
  it("renders missing values as an em dash, never as zero", () => {
    expect(formatMw(null)).toBe("—");
    expect(formatMw(undefined)).toBe("—");
    expect(formatMw(0)).toBe("0 MW"); // a real zero is still a zero
  });
});

describe("toHalfhourlyPoints", () => {
  it("keeps nulls and computes absolute error", () => {
    const points = toHalfhourlyPoints([
      row({}),
      row({ timestamp: "2026-01-01T00:30:00Z", actual_mw: null, error_mw: null, status: "forecast_only" }),
    ]);
    expect(points[0].absError).toBe(1000);
    expect(points[1].actual).toBeNull();
    expect(points[1].absError).toBeNull();
    expect(points[1].label).toBe("00:30 UTC");
  });
});

describe("toDailyPoints", () => {
  it("averages a complete day", () => {
    const points = toDailyPoints([
      row({ settlement_period: 1, actual_mw: 10000, forecast_mw: 11000, error_mw: 1000 }),
      row({ timestamp: "2026-01-01T00:30:00Z", settlement_period: 2, actual_mw: 12000, forecast_mw: 11000, error_mw: -1000 }),
    ]);
    expect(points).toHaveLength(1);
    expect(points[0].forecast).toBe(11000);
    expect(points[0].actual).toBe(11000);
    expect(points[0].error).toBe(0);
    expect(points[0].status).toBe("matched");
    expect(points[0].label).toBe("01 Jan");
  });

  it("never fills a partially-missing day with zero", () => {
    const points = toDailyPoints([
      row({ actual_mw: 10000 }),
      row({ timestamp: "2026-01-01T00:30:00Z", settlement_period: 2, actual_mw: null, error_mw: null, status: "forecast_only" }),
    ]);
    expect(points[0].actual).toBeNull(); // incomplete day -> missing, not 5000
    expect(points[0].forecast).toBe(11000);
    expect(points[0].status).toBe("forecast_only");
    expect(points[0].error).toBeNull();
  });

  it("sorts days ascending", () => {
    const points = toDailyPoints([
      row({ settlement_date: "2026-01-03" }),
      row({ settlement_date: "2026-01-01" }),
      row({ settlement_date: "2026-01-02" }),
    ]);
    expect(points.map((p) => p.label)).toEqual(["01 Jan", "02 Jan", "03 Jan"]);
  });
});

describe("p90AbsError", () => {
  it("returns the nearest-rank 90th-percentile of absolute errors", () => {
    const values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
    const points = values.map((v) => ({
      time: "",
      label: "",
      forecast: null,
      actual: null,
      error: null,
      absError: v,
      status: "matched" as const,
      publishTime: null,
    }));
    // ceil(0.9 * 10) = 9th ordered value
    expect(p90AbsError(points)).toBe(90);
    expect(p90AbsError([])).toBeNull();
  });
});

describe("errorHistogram", () => {
  it("accounts for every non-null interval exactly once", () => {
    const points = [10, 20, 30, 40, 50, 60, null].map((v) => ({
      time: "",
      label: "",
      forecast: null,
      actual: null,
      error: null,
      absError: v,
      status: "matched" as const,
      publishTime: null,
    }));
    const bins = errorHistogram(points, 3);
    const total = bins.reduce((sum, b) => sum + b.count, 0);
    expect(total).toBe(6); // nulls excluded, none double counted
  });
});
