/** Feature B - Forecast error heatmap.
 * Rows = settlement periods (48/day), columns = delivery days. Cells are
 * built by lib/heatmap from the backend rows; missing cells are hatched and
 * visually distinct from a genuine zero error. */
import { useMemo, useState } from "react";
import type { TimeseriesRow } from "../api/types";
import { buildHeatmap, cellColor } from "../lib/heatmap";
import type { HeatmapCell, HeatmapMode } from "../lib/heatmap";
import { formatMw, formatMwSigned, formatUtc } from "../lib/aggregate";

interface Props {
  rows: TimeseriesRow[];
}

interface Hover {
  cell: HeatmapCell;
  x: number;
  y: number;
}

function periodTime(period: number): string {
  const mins = (period - 1) * 30;
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
}

export default function Heatmap({ rows }: Props) {
  const [mode, setMode] = useState<HeatmapMode>("signed");
  const [hover, setHover] = useState<Hover | null>(null);

  const data = useMemo(() => buildHeatmap(rows, mode), [rows, mode]);

  if (data.days.length === 0 || data.cells.length === 0) {
    return (
      <section aria-label="Forecast error heatmap" className="card">
        <h2 className="text-sm font-semibold text-ink-900">Forecast error heatmap</h2>
        <p className="mt-2 text-sm text-ink-500">No half-hourly rows available for the selected range.</p>
      </section>
    );
  }

  const missingCount = data.cells.filter((c) => c.value === null).length;

  return (
    <section aria-label="Forecast error heatmap" className="card">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Forecast error heatmap</h2>
          <p className="text-xs text-ink-500">
            {data.days.length} delivery days × 48 settlement periods. Signed error = forecast − actual;
            positive = over-forecast (amber), negative = under-forecast (blue). Hatched cells have no
            matched value — never zero.
          </p>
        </div>
        <div role="group" aria-label="Heatmap value mode" className="flex gap-1">
          <button
            type="button"
            className={mode === "signed" ? "btn-primary" : "btn"}
            aria-pressed={mode === "signed"}
            onClick={() => setMode("signed")}
          >
            Signed error
          </button>
          <button
            type="button"
            className={mode === "absolute" ? "btn-primary" : "btn"}
            aria-pressed={mode === "absolute"}
            onClick={() => setMode("absolute")}
          >
            Absolute error
          </button>
        </div>
      </div>

      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max gap-1">
          {/* period axis */}
          <div className="flex flex-col pt-0.5 text-[9px] text-ink-500" aria-hidden="true">
            {data.periods.map((p) => (
              <div key={p} className="flex h-2.5 items-center justify-end pr-1 leading-none">
                {p % 6 === 1 ? periodTime(p) : ""}
              </div>
            ))}
          </div>
          {/* day columns */}
          <div className="flex gap-0.5">
            {data.days.map((day) => (
              <div key={day} className="flex flex-col items-center">
                {data.periods.map((p) => {
                  const cell = data.index.get(`${day}|${p}`);
                  const value = cell ? cell.value : null;
                  const present = cell !== undefined;
                  const color = present ? cellColor(value, mode, data.maxAbs) : "transparent";
                  return (
                    <div
                      key={p}
                      role="img"
                      aria-label={
                        present
                          ? `${day} period ${p}: ${
                              value === null
                                ? "missing value"
                                : `${mode === "signed" ? "signed error" : "absolute error"} ${formatMw(value)}`
                            }`
                          : ""
                      }
                      title={
                        cell
                          ? `${formatUtc(cell.timestamp)} · ${
                              value === null ? "missing (no matched value)" : formatMwSigned(value)
                            }`
                          : undefined
                      }
                      className="h-2.5 w-2.5 border"
                      style={{
                        borderColor: "var(--cell-border)",
                        backgroundColor: color,
                        backgroundImage:
                          present && value === null
                            ? "repeating-linear-gradient(45deg, var(--heat-hatch-a) 0 2px, var(--heat-hatch-b) 2px 4px)"
                            : undefined,
                        cursor: cell ? "crosshair" : "default",
                      }}
                      onMouseEnter={(e) => cell && setHover({ cell, x: e.clientX, y: e.clientY })}
                      onMouseLeave={() => setHover(null)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        {/* day axis */}
        <div className="mt-1 flex gap-0.5 pl-6" aria-hidden="true">
          {data.days.map((day, i) => (
            <div key={day} className="w-2.5 text-center text-[8px] leading-tight text-ink-500" style={{ width: 10 }}>
              {i % 3 === 0 ? Number(day.slice(8, 10)) : ""}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-ink-500">
        <div className="flex items-center gap-2">
          <span>{mode === "signed" ? "−" : "0"}</span>
          <div
            className="h-3 w-32 rounded-sm border border-ink-200"
            style={{
              background:
                mode === "signed"
                  ? "linear-gradient(to right, rgba(59,127,196,1), var(--heat-zero), rgba(201,141,30,1))"
                  : "linear-gradient(to right, rgba(59,127,196,0.08), rgba(59,127,196,0.98))",
            }}
          />
          <span>{mode === "signed" ? "+" : formatMw(data.maxAbs)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="h-3 w-4 border border-ink-200"
            style={{ backgroundImage: "repeating-linear-gradient(45deg, var(--heat-hatch-a) 0 2px, var(--heat-hatch-b) 2px 4px)" }}
          />
          <span>missing (no matched value)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-4 border border-ink-200" style={{ backgroundColor: "var(--heat-zero)" }} />
          <span>error ≈ 0 MW</span>
        </div>
        <span>{missingCount} of {data.cells.length} cells missing</span>
        <span>Scale max: {formatMw(data.maxAbs)}</span>
      </div>

      {hover && (
        <div
          className="pointer-events-none fixed z-50 rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md"
          style={{ left: Math.min(hover.x + 14, window.innerWidth - 240), top: hover.y + 14 }}
        >
          <div className="font-semibold text-ink-900">{formatUtc(hover.cell.timestamp)}</div>
          <div className="font-mono">Forecast: {formatMw(hover.cell.forecast)}</div>
          <div className="font-mono">Actual: {formatMw(hover.cell.actual)}</div>
          <div className="font-mono">
            {hover.cell.value === null ? (
              <span className="text-ink-500">Missing — no matched value</span>
            ) : (
              <>Error: {formatMwSigned(hover.cell.value)}</>
            )}
          </div>
          <div className="text-ink-500">status: {hover.cell.status.replace("_", " ")}</div>
        </div>
      )}
    </section>
  );
}
