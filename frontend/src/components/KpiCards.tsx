import type { AccuracyStats } from "../api/types";
import { formatMw, formatMwSigned } from "../lib/aggregate";

interface Props {
  stats: AccuracyStats | null;
  loading: boolean;
}

function Card({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const toneClass =
    tone === "positive"
      ? "text-amberish-600"
      : tone === "negative"
        ? "text-signal-600"
        : "text-ink-900";
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${toneClass}`}>{value}</div>
      <p className="mt-1 text-xs text-ink-500">{hint}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="card animate-pulse" aria-hidden="true">
      <div className="h-3 w-24 rounded bg-ink-200" />
      <div className="mt-3 h-6 w-32 rounded bg-ink-200" />
      <div className="mt-2 h-3 w-40 rounded bg-ink-100" />
    </div>
  );
}

export default function KpiCards({ stats, loading }: Props) {
  if (loading || !stats) {
    return (
      <section aria-label="Key metrics" aria-busy={loading} className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </section>
    );
  }

  const bias = stats.bias_mw;
  const biasLabel = bias === null ? "—" : bias > 0 ? "over-forecast" : bias < 0 ? "under-forecast" : "unbiased";

  return (
    <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
      <Card
        label="Avg forecast"
        value={formatMw(stats.avg_forecast_mw)}
        hint="Decision-time forecast, filtered range"
      />
      <Card
        label="Avg actual"
        value={formatMw(stats.avg_actual_mw)}
        hint="FUELHH outturn (WIND)"
      />
      <Card label="MAE" value={formatMw(stats.mae_mw)} hint="Mean absolute error" />
      <Card label="RMSE" value={formatMw(stats.rmse_mw)} hint="Root mean squared error" />
      <Card
        label="Bias (F − A)"
        value={formatMwSigned(bias)}
        hint={biasLabel}
        tone={bias !== null && bias > 0 ? "positive" : bias !== null && bias < 0 ? "negative" : "neutral"}
      />
      <Card
        label="Coverage"
        value={`${stats.coverage_pct.toFixed(1)}%`}
        hint={`${stats.n_matched} of ${stats.n_expected} intervals matched`}
      />
    </section>
  );
}
