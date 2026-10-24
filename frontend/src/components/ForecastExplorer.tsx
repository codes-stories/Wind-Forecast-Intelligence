/** Feature A - Historical Forecast Vintage Explorer.
 * Shows every WINDFOR publication covering one delivery half-hour:
 * chronological evolution, eligible-at-cutoff vs post-cutoff, and the
 * selected vintage that drives historical error. */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, api } from "../api/client";
import type { VintageIntervalResponse, VintageItem } from "../api/types";
import { formatMw, formatMwSigned, formatUtc } from "../lib/aggregate";
import { useTheme } from "../theme";
import { EmptyState, ErrorPanel, LoadingState } from "./States";

interface Props {
  minDate: string;
  maxDate: string;
  defaultDate: string;
}

interface ChartPoint {
  publish: string; // ISO
  label: string;
  forecast: number | null;
  eligible: boolean;
  selected: boolean;
}

function periodLabel(period: number): string {
  const startMin = (period - 1) * 30;
  const endMin = startMin + 30;
  const fmt = (mins: number) =>
    `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
  return `${fmt(startMin)}–${fmt(endMin)} (period ${period})`;
}

function VintageTooltip({ active, payload }: { active?: boolean; payload?: { payload?: ChartPoint }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-ink-900">Published {formatUtc(point.publish)}</div>
      <div className="font-mono text-ink-800">Forecast: {formatMw(point.forecast)}</div>
      <div className="text-ink-500">
        {point.selected
          ? "Selected vintage (latest eligible at cutoff)"
          : point.eligible
            ? "Eligible at cutoff (superseded)"
            : "Post-cutoff — excluded from historical evaluation"}
      </div>
    </div>
  );
}

function Stat({ label, value, hint, highlight }: { label: string; value: string; hint?: string; highlight?: boolean }) {
  return (
    <div className={highlight ? "card border-signal-500/40 bg-signal-500/5" : "card"}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export default function ForecastExplorer({ minDate, maxDate, defaultDate }: Props) {
  const [date, setDate] = useState(() => (defaultDate >= minDate && defaultDate <= maxDate ? defaultDate : maxDate));
  const [period, setPeriod] = useState(25); // 12:00-12:30
  const [data, setData] = useState<VintageIntervalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .vintages({ date, period }, controller.signal)
      .then((next) => {
        setData(next);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error");
        setLoading(false);
      });
    return () => controller.abort();
  }, [date, period, attempt]);

  const { colors } = useTheme();

  const chartPoints: ChartPoint[] = useMemo(() => {
    if (!data) return [];
    return data.vintages.map((v: VintageItem) => ({
      publish: v.publish_time,
      label: formatUtc(v.publish_time),
      forecast: v.forecast_mw,
      eligible: v.eligible_at_cutoff,
      selected: v.selected,
    }));
  }, [data]);

  const selectedPoint = chartPoints.find((p) => p.selected) ?? null;
  const eligiblePoints = chartPoints.filter((p) => p.eligible && !p.selected);
  const postCutoffPoints = chartPoints.filter((p) => !p.eligible);

  if (error) return <ErrorPanel message={error} onRetry={() => setAttempt((a) => a + 1)} />;
  if (loading && !data) return <LoadingState label="Loading forecast vintages…" />;

  return (
    <div className="space-y-4">
      <section aria-label="Interval selector" className="card flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="explorer-date" className="kpi-label">
            Delivery date (UTC)
          </label>
          <input
            id="explorer-date"
            type="date"
            className="input"
            value={date}
            min={minDate}
            max={maxDate}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="explorer-period" className="kpi-label">
            Settlement interval
          </label>
          <select
            id="explorer-period"
            className="input"
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
          >
            {Array.from({ length: 48 }, (_, i) => i + 1).map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </select>
        </div>
        <p className="ml-auto max-w-md text-xs text-ink-500">
          Every publication covering this interval, chronological. {data?.note}
        </p>
      </section>

      {data?.limitation && <EmptyState message={data.limitation} />}

      {data && !data.limitation && (
        <>
          <section aria-label="Interval summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Delivery interval"
              value={formatUtc(data.delivery_timestamp)}
              hint={`Settlement period ${data.settlement_period} · clock hour ${formatUtc(data.clock_hour, false)}`}
            />
            <Stat
              label="Decision cutoff"
              value={formatUtc(data.cutoff_utc, false)}
              hint={`D−1 ${formatUtc(data.cutoff_utc).split(" ")[0]} · ${data.eligible_count} eligible, ${data.post_cutoff_count} post-cutoff`}
            />
            <Stat
              label="Selected vintage (at cutoff)"
              value={formatMw(data.selected_forecast_mw)}
              hint={
                data.selected_publish_time
                  ? `Published ${formatUtc(data.selected_publish_time)}`
                  : "No eligible publication for this hour"
              }
              highlight
            />
            <Stat
              label="Latest available today"
              value={formatMw(data.latest_forecast_mw)}
              hint={
                data.latest_publish_time
                  ? `Published ${formatUtc(data.latest_publish_time)} — context only, never used for evaluation`
                  : "—"
              }
            />
          </section>

          <section aria-label="Selected vintage error" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Actual (FUELHH)" value={formatMw(data.actual_mw)} hint="Outturn for the interval" />
            <Stat
              label="Signed error (F − A)"
              value={formatMwSigned(data.error_mw)}
              hint={data.error_mw === null ? "Unmatched interval" : data.error_mw > 0 ? "over-forecast" : "under-forecast"}
              highlight
            />
            <Stat label="Absolute error" value={formatMw(data.absolute_error_mw)} hint="Selected vintage vs actual" />
            <Stat
              label="Latest − selected"
              value={formatMwSigned(
                data.latest_forecast_mw !== null && data.selected_forecast_mw !== null
                  ? data.latest_forecast_mw - data.selected_forecast_mw
                  : null,
              )}
              hint="How far the post-cutoff view drifted from the decision"
            />
          </section>

          <section aria-label="Forecast evolution" className="card">
            <div className="mb-3">
              <h2 className="text-sm font-semibold text-ink-900">Forecast evolution by publication time</h2>
              <p className="text-xs text-ink-500">
                Each point is one WINDFOR publication covering this interval: blue = eligible at cutoff,
                amber = published after the cutoff (excluded from historical evaluation), large blue dot =
                the selected vintage. Horizontal dashed line = actual outturn.
              </p>
            </div>
            <div role="img" aria-label="Line chart of forecast values across publication vintages" className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartPoints} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 10, fill: colors.axis }}
                    tickLine={false}
                    angle={-35}
                    textAnchor="end"
                    height={56}
                    interval={0}
                  />
                  <YAxis tick={{ fontSize: 11, fill: colors.axis }} width={56} domain={["auto", "auto"]} />
                  <Tooltip content={<VintageTooltip />} />
                  {data.actual_mw !== null && (
                    <ReferenceLine
                      y={data.actual_mw}
                      stroke={colors.actualRef}
                      strokeDasharray="4 3"
                      label={{ value: "actual", position: "insideTopLeft", fontSize: 10, fill: colors.actualRef }}
                    />
                  )}
                  <Line
                    type="stepAfter"
                    dataKey="forecast"
                    name="Forecast (MW)"
                    stroke={colors.reference}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Scatter
                    data={eligiblePoints}
                    dataKey="forecast"
                    fill={colors.eligible}
                    shape="circle"
                    isAnimationActive={false}
                  />
                  <Scatter
                    data={postCutoffPoints}
                    dataKey="forecast"
                    fill={colors.postCutoff}
                    shape="circle"
                    isAnimationActive={false}
                  />
                  {selectedPoint && (
                    <Scatter
                      data={[selectedPoint]}
                      dataKey="forecast"
                      fill={colors.selected}
                      shape="circle"
                      isAnimationActive={false}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-xs text-ink-500">
              {data.eligible_count} publication{data.eligible_count === 1 ? "" : "s"} eligible at the cutoff,{" "}
              {data.post_cutoff_count} published after it. Selection rule: latest vintage with
              publishTime ≤ cutoff (09:20 UTC on D−1). Publication timestamps are never rewritten.
            </p>
          </section>

          <section aria-label="Publication history" className="card overflow-x-auto">
            <div className="mb-3">
              <h2 className="text-sm font-semibold text-ink-900">Publication history</h2>
              <p className="text-xs text-ink-500">
                Δ = change vs the previous publication. Post-cutoff rows are shown for context only.
              </p>
            </div>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-500">
                  <th scope="col" className="py-2 pr-4">Published (UTC)</th>
                  <th scope="col" className="py-2 pr-4 text-right">Forecast (MW)</th>
                  <th scope="col" className="py-2 pr-4 text-right">Δ vs previous</th>
                  <th scope="col" className="py-2">Eligibility</th>
                </tr>
              </thead>
              <tbody>
                {data.vintages.map((v) => (
                  <tr
                    key={v.publish_time}
                    className={`border-b border-ink-100 ${v.selected ? "bg-signal-500/5" : ""}`}
                  >
                    <td className="py-2 pr-4 font-mono text-xs">{formatUtc(v.publish_time)}</td>
                    <td className="py-2 pr-4 text-right font-mono">{formatMw(v.forecast_mw)}</td>
                    <td className="py-2 pr-4 text-right font-mono">{formatMwSigned(v.change_mw)}</td>
                    <td className="py-2">
                      {v.selected && (
                        <span className="badge bg-signal-500/10 text-signal-600">selected (at cutoff)</span>
                      )}
                      {!v.selected && v.eligible_at_cutoff && (
                        <span className="badge bg-ink-100 text-ink-700">eligible, superseded</span>
                      )}
                      {!v.eligible_at_cutoff && (
                        <span className="badge bg-amberish-500/10 text-amberish-600">post-cutoff, excluded</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
