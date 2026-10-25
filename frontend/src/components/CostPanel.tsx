/** Headline £ value of the forecast error + per-day bars.
 *
 *  Totals are derived from the half-hourly rows (error x day-ahead price x
 *  interval hours) so the headline always equals the sum of the daily bars,
 *  at any aggregation. Availability/coverage/source come from the backend
 *  accuracy stats. The figure is an indicative valuation at day-ahead
 *  market-index prices - never an imbalance settlement number. */
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AccuracyResponse, TimeseriesRow } from "../api/types";
import { formatDay, formatGbp, formatGbpCompact } from "../lib/aggregate";
import { useTheme } from "../theme";

interface Props {
  rows: TimeseriesRow[];
  stats: AccuracyResponse;
}

interface DayCost {
  day: string;
  label: string;
  net: number;
  abs: number;
  priced: number;
}

interface TipPayload {
  payload?: DayCost;
}

function DayTooltip({ active, payload }: { active?: boolean; payload?: TipPayload[] }) {
  const day = payload?.[0]?.payload;
  if (!active || !day) return null;
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-ink-900">{day.label} (UTC day)</div>
      <div className="mt-1 font-mono text-ink-700">Net value: {formatGbp(day.net)}</div>
      <div className="font-mono text-ink-700">Absolute value: {formatGbp(day.abs)}</div>
      <div className="mt-1 text-ink-500">
        {day.priced} priced half-hourly intervals
      </div>
    </div>
  );
}

export default function CostPanel({ rows, stats }: Props) {
  const { colors } = useTheme();

  const days = useMemo<DayCost[]>(() => {
    const byDay = new Map<string, { net: number; abs: number; priced: number }>();
    for (const row of rows) {
      const value = row.error_value_gbp;
      if (value === null || value === undefined) continue;
      const bucket = byDay.get(row.settlement_date) ?? { net: 0, abs: 0, priced: 0 };
      bucket.net += value;
      bucket.abs += Math.abs(value);
      bucket.priced += 1;
      byDay.set(row.settlement_date, bucket);
    }
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, bucket]) => ({ day, label: formatDay(day), ...bucket }));
  }, [rows]);

  const totalAbs = days.reduce((sum, d) => sum + d.abs, 0);
  const totalNet = days.reduce((sum, d) => sum + d.net, 0);

  // Price feed unavailable -> the backend reports null £ totals; the accuracy
  // note already explains it, so this panel stays out of the way.
  if (stats.abs_error_value_gbp === null || stats.abs_error_value_gbp === undefined) {
    return null;
  }

  return (
    <section aria-label="Value of forecast error" className="card">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Value of forecast error (£)</h2>
          <p className="text-xs text-ink-500">
            Error valued at the day-ahead market-index price x interval hours, summed over the
            filtered range
          </p>
        </div>
        <p className="text-xs text-ink-500">
          {stats.n_priced_intervals ?? 0} priced of {stats.n_matched} matched intervals (
          {(stats.price_coverage_pct ?? 0).toFixed(1)}% price coverage)
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-3">
          <div>
            <div className="kpi-label">Absolute value of error</div>
            <div className="kpi-value text-ink-900">{formatGbpCompact(totalAbs)}</div>
            <p className="mt-1 text-xs text-ink-500">
              Gross cost of being wrong: Σ|error| x £/MWh x hours
            </p>
          </div>
          <div>
            <div className="kpi-label">Net (signed) value</div>
            <div
              className={`kpi-value ${totalNet > 0 ? "text-amberish-600" : totalNet < 0 ? "text-signal-600" : "text-ink-900"}`}
            >
              {formatGbpCompact(totalNet)}
            </div>
            <p className="mt-1 text-xs text-ink-500">
              {totalNet > 0
                ? "Over-forecast direction: forecast above outturn"
                : totalNet < 0
                  ? "Under-forecast direction: forecast below outturn"
                  : "Balanced over the range"}
            </p>
          </div>
          <p className="text-[11px] leading-relaxed text-ink-400">
            Indicative valuation at {stats.price_source ?? "day-ahead market-index prices"} — not
            an imbalance settlement figure.
          </p>
        </div>

        <div className="lg:col-span-2">
          {days.length > 0 ? (
            <>
              <div
                role="img"
                aria-label="Bar chart of the daily pound value of forecast error"
                className="h-56"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={days} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                    <XAxis
                      dataKey="label"
                      interval={Math.max(0, Math.ceil(days.length / 8) - 1)}
                      tick={{ fontSize: 11, fill: colors.axis }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: colors.axis }}
                      tickFormatter={(v: number) => formatGbpCompact(v)}
                      width={72}
                    />
                    <Tooltip content={<DayTooltip />} />
                    <ReferenceLine y={0} stroke={colors.reference} />
                    <Bar dataKey="net" name="Net value of error" isAnimationActive={false}>
                      {days.map((day) => (
                        <Cell
                          key={day.day}
                          fill={day.net >= 0 ? colors.flag : colors.actualRef}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-[11px] text-ink-400">
                Daily sums of the half-hourly row values; gaps in priced intervals are excluded,
                never zero-filled.
              </p>
            </>
          ) : (
            <p className="text-xs text-ink-500" role="status">
              No priced intervals in this range — the £ breakdown is unavailable.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
