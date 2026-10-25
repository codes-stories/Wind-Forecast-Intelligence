/** Chart/table point derivation from API rows.
 *  Daily values are means of the day's half-hourly rows and are only emitted when
 *  every source row is present - missing data stays missing (never zero-filled). */
import type { TimeseriesRow } from "../api/types";

export interface ChartPoint {
  time: string; // ISO delivery timestamp (or date at daily grain)
  label: string; // x-axis label
  forecast: number | null;
  actual: number | null;
  error: number | null;
  absError: number | null;
  status: TimeseriesRow["status"];
  publishTime: string | null;
}

const nf = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

export function formatMw(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${nf.format(value)} MW`;
}

/** Full pound figure, e.g. "£152,213,719" (null-safe: "—"). */
export function formatGbp(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return gbp.format(value);
}

/** Compact pound figure for headlines, e.g. "£152.2m" (null-safe: "—"). */
export function formatGbpCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}£${(abs / 1e9).toFixed(1)}bn`;
  if (abs >= 1e6) return `${sign}£${(abs / 1e6).toFixed(1)}m`;
  if (abs >= 1e3) return `${sign}£${nf.format(Math.round(abs / 1e3))}k`;
  return gbp.format(value);
}

export function formatMwSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${nf1.format(value)} MW`;
}

/** "2026-01-15T10:30:00Z" -> "15 Jan 10:30 UTC" */
export function formatUtc(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  if (!withDate) return `${hh}:${mm} UTC`;
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
  return `${day} ${month} ${hh}:${mm} UTC`;
}

export function formatDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
  return `${day} ${month}`;
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

/** Half-hourly rows -> chart points (labels are UTC times). */
export function toHalfhourlyPoints(rows: TimeseriesRow[]): ChartPoint[] {
  return rows.map((row) => ({
    time: row.timestamp,
    label: formatUtc(row.timestamp, false),
    forecast: row.forecast_mw,
    actual: row.actual_mw,
    error: row.error_mw,
    absError: row.error_mw === null ? null : Math.abs(row.error_mw),
    status: row.status,
    publishTime: row.forecast_publish_time,
  }));
}

/** Half-hourly rows -> daily means (null unless every row of the day is present). */
export function toDailyPoints(rows: TimeseriesRow[]): ChartPoint[] {
  const byDay = new Map<string, TimeseriesRow[]>();
  for (const row of rows) {
    const bucket = byDay.get(row.settlement_date) ?? [];
    bucket.push(row);
    byDay.set(row.settlement_date, bucket);
  }
  const points: ChartPoint[] = [];
  for (const [day, dayRows] of [...byDay.entries()].sort()) {
    const forecasts = dayRows.map((r) => r.forecast_mw);
    const actuals = dayRows.map((r) => r.actual_mw);
    const complete = (values: (number | null)[]) =>
      values.every((v) => v !== null) ? (values as number[]) : [];
    const forecastValues = complete(forecasts);
    const actualValues = complete(actuals);
    const forecast = mean(forecastValues);
    const actual = mean(actualValues);
    const error = forecast !== null && actual !== null ? forecast - actual : null;
    const status: TimeseriesRow["status"] =
      error !== null
        ? "matched"
        : forecast !== null
          ? "forecast_only"
          : actual !== null
            ? "actual_only"
            : "missing_both";
    const publishes = dayRows
      .map((r) => r.forecast_publish_time)
      .filter((p): p is string => p !== null)
      .sort();
    points.push({
      time: `${day}T00:00:00Z`,
      label: formatDay(day),
      forecast,
      actual,
      error,
      absError: error === null ? null : Math.abs(error),
      status,
      publishTime: publishes.length ? publishes[publishes.length - 1] : null,
    });
  }
  return points;
}

/** 90th-percentile threshold of |error| - the transparent "large error" highlight rule. */
export function p90AbsError(points: ChartPoint[]): number | null {
  const values = points
    .map((p) => p.absError)
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
  if (values.length === 0) return null;
  const index = Math.min(values.length - 1, Math.ceil(0.9 * values.length) - 1);
  return values[Math.max(0, index)];
}

/** Histogram of |error| for the distribution chart. */
export function errorHistogram(points: ChartPoint[], bins = 6): { label: string; count: number }[] {
  const values = points
    .map((p) => p.absError)
    .filter((v): v is number => v !== null);
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return [{ label: `${nf.format(min)} MW`, count: values.length }];
  }
  const width = (max - min) / bins;
  const counts = new Array(bins).fill(0) as number[];
  for (const v of values) {
    const idx = Math.min(bins - 1, Math.floor((v - min) / width));
    counts[idx] += 1;
  }
  return counts.map((count, i) => {
    const lo = min + i * width;
    const hi = lo + width;
    return { label: `${nf.format(lo)}–${nf.format(hi)}`, count };
  });
}
