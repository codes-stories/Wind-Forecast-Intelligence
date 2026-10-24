/** Heatmap data preparation (Feature B).
 *
 * Cells are derived from the backend half-hourly rows only - no metric is
 * recalculated here beyond taking the absolute value of the signed error
 * the backend already computed. Missing values stay null (rendered as a
 * distinct hatched cell, never as zero). */
import type { TimeseriesRow } from "../api/types";

export type HeatmapMode = "signed" | "absolute";

export interface HeatmapCell {
  day: string; // settlement_date (YYYY-MM-DD)
  period: number; // settlement period 1..48
  timestamp: string;
  /** signed error (forecast - actual) in "signed" mode, |error| in "absolute" mode; null when unmatched */
  value: number | null;
  status: TimeseriesRow["status"];
  forecast: number | null;
  actual: number | null;
}

export interface HeatmapData {
  days: string[]; // unique settlement dates, sorted ascending
  periods: number[]; // 1..48
  cells: HeatmapCell[];
  /** "day|period" index for O(1) lookup while rendering */
  index: Map<string, HeatmapCell>;
  maxAbs: number; // max |value| over present cells (0 when none)
}

export function toHeatmapCells(rows: TimeseriesRow[], mode: HeatmapMode): HeatmapCell[] {
  return rows.map((row) => ({
    day: row.settlement_date,
    period: row.settlement_period ?? 0,
    timestamp: row.timestamp,
    value:
      row.error_mw === null ? null : mode === "signed" ? row.error_mw : Math.abs(row.error_mw),
    status: row.status,
    forecast: row.forecast_mw,
    actual: row.actual_mw,
  }));
}

export function buildHeatmap(rows: TimeseriesRow[], mode: HeatmapMode): HeatmapData {
  const cells = toHeatmapCells(rows, mode);
  const days = [...new Set(cells.map((c) => c.day))].sort();
  const periods = Array.from({ length: 48 }, (_, i) => i + 1);
  const index = new Map<string, HeatmapCell>();
  for (const cell of cells) index.set(`${cell.day}|${cell.period}`, cell);
  let maxAbs = 0;
  for (const cell of cells) {
    if (cell.value !== null && Math.abs(cell.value) > maxAbs) maxAbs = Math.abs(cell.value);
  }
  return { days, periods, cells, index, maxAbs };
}

function clamp01(t: number): number {
  return Math.max(0, Math.min(1, t));
}

/** Diverging (signed) / sequential (absolute) colour; null -> "" (hatched missing). */
export function cellColor(value: number | null, mode: HeatmapMode, maxAbs: number): string {
  if (value === null) return "";
  if (maxAbs <= 0) return "#f4f6f9";
  const t = clamp01(Math.abs(value) / maxAbs);
  if (mode === "absolute") {
    return `rgba(59, 127, 196, ${(0.08 + 0.9 * t).toFixed(3)})`;
  }
  if (Math.abs(value) < 1e-9) return "#f4f6f9"; // genuine zero error: neutral, not missing
  if (value > 0) return `rgba(201, 141, 30, ${(0.15 + 0.85 * t).toFixed(3)})`; // over-forecast
  return `rgba(59, 127, 196, ${(0.15 + 0.85 * t).toFixed(3)})`; // under-forecast
}
