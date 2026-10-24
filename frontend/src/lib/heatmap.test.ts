import { describe, expect, it } from "vitest";
import type { TimeseriesRow } from "../api/types";
import { buildHeatmap, cellColor, toHeatmapCells } from "./heatmap";

function row(overrides: Partial<TimeseriesRow>): TimeseriesRow {
  return {
    timestamp: "2026-01-15T10:00:00Z",
    settlement_date: "2026-01-15",
    settlement_period: 21,
    actual_mw: 10000,
    forecast_mw: 11000,
    error_mw: 1000,
    status: "matched",
    forecast_publish_time: "2026-01-14T07:30:00Z",
    ...overrides,
  };
}

describe("toHeatmapCells", () => {
  it("keeps signed errors (forecast - actual) in signed mode", () => {
    const cells = toHeatmapCells([row({ error_mw: -250 })], "signed");
    expect(cells[0].value).toBe(-250);
    expect(cells[0].day).toBe("2026-01-15");
    expect(cells[0].period).toBe(21);
    expect(cells[0].forecast).toBe(11000);
    expect(cells[0].actual).toBe(10000);
  });

  it("uses absolute errors in absolute mode", () => {
    const cells = toHeatmapCells([row({ error_mw: -250 }), row({ error_mw: 900 })], "absolute");
    expect(cells.map((c) => c.value)).toEqual([250, 900]);
  });

  it("keeps missing errors null - never zero-filled", () => {
    const cells = toHeatmapCells([row({ error_mw: null, actual_mw: null, status: "forecast_only" })], "signed");
    expect(cells[0].value).toBeNull();
    expect(cells[0].value).not.toBe(0);
  });

  it("maps missing settlement_period to period 0 rather than a wrong slot", () => {
    const cells = toHeatmapCells([row({ settlement_period: null })], "signed");
    expect(cells[0].period).toBe(0);
  });
});

describe("buildHeatmap", () => {
  const rows = [
    row({ settlement_date: "2026-01-02", timestamp: "2026-01-02T00:00:00Z", settlement_period: 1, error_mw: -500 }),
    row({ settlement_date: "2026-01-01", timestamp: "2026-01-01T00:00:00Z", settlement_period: 1, error_mw: 300 }),
    row({ settlement_date: "2026-01-01", timestamp: "2026-01-01T00:30:00Z", settlement_period: 2, error_mw: null }),
  ];

  it("sorts days, keeps all48 period slots and indexes cells by day|period", () => {
    const data = buildHeatmap(rows, "signed");
    expect(data.days).toEqual(["2026-01-01", "2026-01-02"]);
    expect(data.periods).toHaveLength(48);
    expect(data.periods[0]).toBe(1);
    expect(data.periods[47]).toBe(48);
    expect(data.index.get("2026-01-01|1")?.value).toBe(300);
    expect(data.index.get("2026-01-01|2")?.value).toBeNull(); // missing stays missing
    expect(data.index.get("2026-01-02|3")).toBeUndefined(); // absent cell (not in rows)
  });

  it("computes maxAbs over present values only (nulls ignored)", () => {
    const data = buildHeatmap(rows, "signed");
    expect(data.maxAbs).toBe(500);
    const abs = buildHeatmap(rows, "absolute");
    expect(abs.maxAbs).toBe(500);
  });

  it("maxAbs is 0 when every value is missing", () => {
    const data = buildHeatmap([row({ error_mw: null })], "signed");
    expect(data.maxAbs).toBe(0);
  });
});

describe("cellColor", () => {
  it("returns an empty string for missing cells (hatched, distinct from zero)", () => {
    expect(cellColor(null, "signed", 1000)).toBe("");
    expect(cellColor(null, "absolute", 1000)).toBe("");
  });

  it("genuine zero error gets a themed neutral fill, not the missing style", () => {
    const zero = cellColor(0, "signed", 1000);
    expect(zero).not.toBe("");
    expect(zero).toBe("var(--heat-zero)"); // light/dark resolved by CSS
  });

  it("signed mode diverges: positive (over) amber vs negative (under) blue", () => {
    const over = cellColor(800, "signed", 1000);
    const under = cellColor(-800, "signed", 1000);
    expect(over).toContain("201, 141, 30"); // amber
    expect(under).toContain("59, 127, 196"); // blue
    // intensity grows with magnitude toward the max
    expect(cellColor(200, "signed", 1000)).not.toBe(cellColor(800, "signed", 1000));
  });

  it("absolute mode is a sequential blue scale", () => {
    expect(cellColor(100, "absolute", 1000)).toContain("59, 127, 196");
    expect(cellColor(1000, "absolute", 1000)).toContain("59, 127, 196");
  });

  it("all-missing data (maxAbs 0) still yields themed neutral fills for present values", () => {
    expect(cellColor(0, "absolute", 0)).toBe("var(--heat-zero)");
  });
});
