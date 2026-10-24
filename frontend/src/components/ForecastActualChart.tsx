import {
  Area,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartPoint } from "../lib/aggregate";
import { formatMw, formatUtc } from "../lib/aggregate";
import { useTheme } from "../theme";
import type { Aggregation } from "./FilterBar";

interface Props {
  points: ChartPoint[];
  aggregation: Aggregation;
}

interface TipPayload {
  payload?: ChartPoint;
}

function ChartTooltip({
  active,
  payload,
  aggregation,
}: {
  active?: boolean;
  payload?: TipPayload[];
  aggregation: Aggregation;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const when = aggregation === "daily" ? `${point.label} (UTC day)` : `${point.label} — delivery interval (UTC)`;
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-ink-900">{when}</div>
      <div className="mt-1 font-mono text-signal-600">Forecast: {formatMw(point.forecast)}</div>
      <div className="font-mono text-amberish-600">Actual: {formatMw(point.actual)}</div>
      <div className="font-mono text-ink-700">
        Error (F − A): {point.error === null ? "—" : `${point.error > 0 ? "+" : ""}${formatMw(point.error)}`}
      </div>
      <div className="mt-1 text-ink-500">Forecast published: {formatUtc(point.publishTime)}</div>
      {point.status !== "matched" && (
        <div className="mt-1 text-amberish-600">Missing data ({point.status}) — not zero</div>
      )}
    </div>
  );
}

export default function ForecastActualChart({ points, aggregation }: Props) {
  const { colors } = useTheme();
  const tickInterval = Math.max(0, Math.ceil(points.length / 8) - 1);
  return (
    <div className="card">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Forecast vs actual generation</h2>
          <p className="text-xs text-ink-500">
            {aggregation === "daily"
              ? "Daily mean generation across delivery intervals (MW)"
              : "Half-hourly generation, delivery intervals in UTC (MW)"}
          </p>
        </div>
        <p className="text-xs text-ink-500">Gaps indicate missing data — never plotted as zero</p>
      </div>
      <div role="img" aria-label="Line chart comparing forecast and actual wind generation" className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="label"
              interval={tickInterval}
              tick={{ fontSize: 11, fill: colors.axis }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: colors.axis }}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
              width={48}
              label={{ value: "MW", position: "insideTopLeft", fontSize: 11, fill: colors.axis }}
            />
            <Tooltip content={<ChartTooltip aggregation={aggregation} />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              type="monotone"
              dataKey="forecast"
              name="Forecast (decision-time)"
              stroke={colors.forecast}
              fill={colors.forecast}
              fillOpacity={0.12}
              strokeWidth={1.6}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual (FUELHH WIND)"
              stroke={colors.actual}
              strokeWidth={1.6}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
