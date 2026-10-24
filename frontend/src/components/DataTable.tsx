import { useEffect, useMemo, useState } from "react";
import type { ChartPoint } from "../lib/aggregate";
import { formatMw, formatMwSigned, formatUtc } from "../lib/aggregate";

interface Props {
  points: ChartPoint[];
  pageSize?: number;
  /** true when points are daily aggregates (delivery day, not timestamp) */
  daily?: boolean;
}

type SortKey = "time" | "forecast" | "actual" | "error" | "absError" | "publishTime" | "status";

interface Column {
  key: SortKey;
  label: string;
  numeric: boolean;
}

const COLUMNS: Column[] = [
  { key: "time", label: "Delivery timestamp (UTC)", numeric: false },
  { key: "forecast", label: "Forecast (MW)", numeric: true },
  { key: "actual", label: "Actual (MW)", numeric: true },
  { key: "error", label: "Signed error F − A (MW)", numeric: true },
  { key: "absError", label: "Absolute error (MW)", numeric: true },
  { key: "publishTime", label: "Forecast published (UTC)", numeric: false },
  { key: "status", label: "Availability", numeric: false },
];

const STATUS_BADGE: Record<ChartPoint["status"], { label: string; className: string }> = {
  matched: { label: "matched", className: "bg-ink-100 text-ink-700" },
  forecast_only: { label: "forecast only", className: "bg-signal-500/10 text-signal-600" },
  actual_only: { label: "actual only", className: "bg-amberish-400/15 text-amberish-600" },
  missing_both: { label: "missing both", className: "bg-red-100 text-red-700" },
};

function compare(a: ChartPoint, b: ChartPoint, key: SortKey): number {
  const av = a[key];
  const bv = b[key];
  if (av === null && bv === null) return 0;
  if (av === null) return 1; // nulls last
  if (bv === null) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  return String(av).localeCompare(String(bv));
}

export default function DataTable({ points, pageSize = 25, daily = false }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(0);

  useEffect(() => {
    setPage(0);
  }, [points, sortKey, sortDir]);

  const sorted = useMemo(() => {
    const copy = [...points].sort((a, b) => {
      const cmp = compare(a, b, sortKey);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [points, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "time" ? "asc" : "desc");
    }
  };

  return (
    <div className="card">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Historical delivery data</h2>
          <p className="text-xs text-ink-500">
            {sorted.length} rows · values from the API for the selected range · “—” means missing, not zero
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-600">
          <button type="button" className="btn" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safePage === 0}>
            Previous
          </button>
          <span aria-live="polite">
            Page {safePage + 1} of {pageCount}
          </span>
          <button
            type="button"
            className="btn"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={safePage >= pageCount - 1}
          >
            Next
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-500">
              {COLUMNS.map((col) => {
                const active = sortKey === col.key;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                    className={col.numeric ? "py-2 pr-3 text-right" : "py-2 pr-3"}
                  >
                    <button
                      type="button"
                      className={`inline-flex items-center gap-1 hover:text-ink-800 ${active ? "text-ink-900" : ""}`}
                      onClick={() => toggleSort(col.key)}
                    >
                      {col.key === "time" && daily ? "Delivery day (UTC)" : col.label}
                      <span aria-hidden="true" className="text-[10px]">
                        {active ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((point) => {
              const badge = STATUS_BADGE[point.status];
              return (
                <tr key={point.time} className="border-b border-ink-100 hover:bg-ink-50">
                  <td className="py-2 pr-3 font-mono text-xs text-ink-800">
                    {daily ? point.label : formatUtc(point.time)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">{formatMw(point.forecast)}</td>
                  <td className="py-2 pr-3 text-right font-mono">{formatMw(point.actual)}</td>
                  <td className="py-2 pr-3 text-right font-mono">{formatMwSigned(point.error)}</td>
                  <td className="py-2 pr-3 text-right font-mono">{formatMw(point.absError)}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-ink-600">{formatUtc(point.publishTime)}</td>
                  <td className="py-2 pr-3">
                    <span className={`badge ${badge.className}`}>{badge.label}</span>
                  </td>
                </tr>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="py-4 text-center text-sm text-ink-500">
                  No rows for the selected range.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
