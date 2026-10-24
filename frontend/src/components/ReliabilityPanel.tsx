/** Feature C - Reliability / risk indicators with explicit interpretations.
 * Values come from the backend accuracy response (same matched sample as the
 * KPI cards); this panel adds dispersion and missing-data indicators. */
import type { AccuracyResponse } from "../api/types";
import { formatMw } from "../lib/aggregate";

interface Props {
  stats: AccuracyResponse | null;
}

interface Metric {
  label: string;
  value: string;
  title: string;
}

function Cell({ label, value, title, hint }: { label: string; value: string; title: string; hint?: string }) {
  return (
    <div className="card" title={title}>
      <div className="kpi-label flex items-center gap-1">
        {label}
        <span aria-hidden="true" className="text-ink-400">ⓘ</span>
        <span className="sr-only">{title}</span>
      </div>
      <div className="kpi-value">{value}</div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export default function ReliabilityPanel({ stats }: Props) {
  if (!stats) return null;

  const metrics: Metric[] = [
    {
      label: "Median |error|",
      value: formatMw(stats.median_abs_error_mw),
      title:
        "Median absolute error over matched intervals: half of the intervals had a smaller " +
        "absolute miss than this. A historical statistic for the selected range.",
    },
    {
      label: "p90 |error|",
      value: stats.p90_abs_error_mw === null ? "—" : formatMw(stats.p90_abs_error_mw),
      title:
        "90th percentile (nearest-rank) of absolute error over matched intervals: 10% of " +
        "intervals had a larger miss. Historical error statistic, NOT a calibrated confidence " +
        "interval or a guarantee for future errors. Shown only with ≥10 matched intervals.",
    },
    {
      label: "RMSE − MAE",
      value:
        stats.rmse_mw !== null && stats.mae_mw !== null
          ? formatMw(Number((stats.rmse_mw - stats.mae_mw).toFixed(3)))
          : "—",
      title:
        "Gap between RMSE and MAE: a large gap means a few big misses dominate the RMSE " +
        "(squared errors weight tails heavily).",
    },
    {
      label: "Matched intervals",
      value: `${stats.n_matched} / ${stats.n_expected}`,
      title:
        "Intervals with both a decision-time forecast and an actual outturn, out of the " +
        "intervals expected in the selected range.",
    },
    {
      label: "Missing actual",
      value: String(stats.n_missing_actual),
      title:
        "Intervals where a forecast exists but no actual outturn was retrieved. These are " +
        "excluded from all metrics and shown as 'forecast only' in the table (never as zero).",
    },
    {
      label: "Missing forecast",
      value: String(stats.n_missing_forecast),
      title:
        "Intervals where an actual exists but no eligible forecast publication covered the " +
        "interval. Excluded from metrics; shown as 'actual only' (never backfilled).",
    },
    {
      label: "MAPE excluded",
      value: String(stats.mape_excluded_intervals),
      title:
        "Matched intervals excluded from MAPE because the actual was zero (undefined ratio). " +
        "Excluded intervals still count toward MAE/RMSE/bias.",
    },
    {
      label: "MAPE",
      value: stats.mape_pct === null ? "—" : `${stats.mape_pct.toFixed(1)}%`,
      title:
        "Mean absolute percentage error over matched intervals with non-zero actuals. " +
        "Percentage error over-weights low-wind intervals; prefer MW-based indicators for " +
        "operational risk.",
    },
  ];

  return (
    <section aria-label="Reliability indicators" className="space-y-2">
      <div>
        <h2 className="text-sm font-semibold text-ink-900">Reliability &amp; risk indicators</h2>
        <p className="text-xs text-ink-500">
          Same matched sample as the metrics above. Percentiles describe this historical range only —
          they are not confidence intervals. Hover a card for its definition.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((m) => (
          <Cell key={m.label} label={m.label} value={m.value} title={m.title} />
        ))}
      </div>
    </section>
  );
}
