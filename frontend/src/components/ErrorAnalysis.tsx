import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPoint } from "../lib/aggregate";
import { errorHistogram, formatMw, formatMwSigned, p90AbsError } from "../lib/aggregate";
import { useTheme } from "../theme";
import type { Aggregation } from "./FilterBar";

interface Props {
  points: ChartPoint[];
  aggregation: Aggregation;
}

function ErrorTooltip({ active, payload }: { active?: boolean; payload?: { payload?: ChartPoint }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const direction = point.error === null ? "" : point.error > 0 ? "over-forecast" : "under-forecast";
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-ink-900">{point.label}</div>
      <div className="font-mono text-ink-800">Signed error: {formatMwSigned(point.error)}</div>
      <div className="font-mono text-ink-700">Absolute error: {formatMw(point.absError)}</div>
      {direction && <div className="text-ink-500">{direction} (forecast − actual)</div>}
    </div>
  );
}

function HistTooltip({ active, payload }: { active?: boolean; payload?: { payload?: { label: string; count: number } }[] }) {
  const bin = payload?.[0]?.payload;
  if (!active || !bin) return null;
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold">|Error| {bin.label}</div>
      <div className="font-mono">{bin.count} intervals</div>
    </div>
  );
}

export default function ErrorAnalysis({ points, aggregation }: Props) {
  const { colors } = useTheme();
  const BASE_BAR = colors.bar;
  const FLAG_BAR = colors.flag;
  const threshold = p90AbsError(points);
  const histogram = errorHistogram(points);
  const flagged = threshold === null ? 0 : points.filter((p) => (p.absError ?? -1) >= threshold).length;
  const tickInterval = Math.max(0, Math.ceil(points.length / 7) - 1);

  return (
    <section aria-label="Forecast error analysis" className="grid gap-3 lg:grid-cols-2">
      <div className="card">
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-ink-900">Signed error over time</h2>
          <p className="text-xs text-ink-500">
            Forecast − actual (MW). Positive = over-forecast. Amber bars are flagged by the rule below.
          </p>
        </div>
        <div role="img" aria-label="Bar chart of signed forecast error over time" className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="label" interval={tickInterval} tick={{ fontSize: 11, fill: colors.axis }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: colors.axis }} width={56} />
              <Tooltip content={<ErrorTooltip />} />
              <ReferenceLine y={0} stroke={colors.reference} />
              <Bar dataKey="error" name="Signed error (MW)" isAnimationActive={false}>
                {points.map((point) => (
                  <Cell
                    key={point.time}
                    fill={threshold !== null && point.absError !== null && point.absError >= threshold ? FLAG_BAR : BASE_BAR}
                    fillOpacity={point.error === null ? 0 : 1}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-ink-500">
          Highlight rule (transparent): |error| ≥ 90th percentile of the filtered range
          {threshold !== null ? ` = ${formatMw(threshold)} (${flagged} of ${points.length} shown)` : ""}.
        </p>
      </div>

      <div className="card">
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-ink-900">Absolute error distribution</h2>
          <p className="text-xs text-ink-500">
            Count of {aggregation === "daily" ? "days" : "intervals"} per absolute-error band (MW)
          </p>
        </div>
        <div role="img" aria-label="Histogram of absolute forecast error" className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={histogram} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: colors.axis }} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: colors.axis }} width={40} />
              <Tooltip content={<HistTooltip />} />
              <Bar dataKey="count" name="Intervals" fill={BASE_BAR} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-ink-500">
          MAPE excludes intervals where actual = 0 (backend reports the exclusion count; January 2026 has none).
        </p>
      </div>
    </section>
  );
}
