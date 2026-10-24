/** Feature E - Evidence-based automatic insights (deterministic, backend-computed).
 * This component only renders findings returned by GET /api/insights; every
 * insight carries its evidence, period and interpretation. */
import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { InsightItem, InsightsResponse } from "../api/types";

interface Props {
  start: string;
  end: string;
  grain: string;
}

const ID_LABELS: Record<string, string> = {
  bias_direction: "Bias",
  coverage: "Coverage",
  worst_mae_day: "Worst day",
  daily_mae_spread: "Day-to-day spread",
  largest_abs_error: "Largest miss",
  error_concentration: "Error tail",
};

function InsightCard({ item }: { item: InsightItem }) {
  const label = ID_LABELS[item.id] ?? item.id;
  if (!item.available) {
    return (
      <li className="rounded-lg border border-dashed border-ink-200 bg-ink-50 p-3 opacity-80">
        <div className="flex items-center gap-2">
          <span className="badge bg-ink-100 text-ink-600">{label}</span>
          <span className="text-xs font-medium text-ink-600">{item.finding}</span>
        </div>
        {item.unavailable_reason && (
          <p className="mt-1 text-xs text-ink-500">{item.unavailable_reason}</p>
        )}
      </li>
    );
  }
  return (
    <li className="card">
      <div className="flex items-center gap-2">
        <span className="badge bg-signal-500/10 text-signal-600">{label}</span>
        <span className="text-sm font-semibold text-ink-900">{item.finding}</span>
      </div>
      <p className="mt-2 font-mono text-xs text-ink-700">{item.evidence}</p>
      <p className="mt-2 text-xs text-ink-500">{item.why_it_matters}</p>
      <p className="mt-1 text-[11px] text-ink-400">Period: {item.period}</p>
    </li>
  );
}

export default function Insights({ start, end, grain }: Props) {
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    api
      .insights({ start, end, grain }, controller.signal)
      .then(setData)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error");
        setData(null);
      });
    return () => controller.abort();
  }, [start, end, grain, attempt]);

  if (error) {
    return (
      <section aria-label="Automatic insights" className="card">
        <h2 className="text-sm font-semibold text-ink-900">What the data shows</h2>
        <p className="mt-2 text-xs text-ink-500" role="status">
          Insights unavailable ({error}).{" "}
          <button type="button" className="underline" onClick={() => setAttempt((a) => a + 1)}>
            Retry
          </button>
        </p>
      </section>
    );
  }
  if (!data) {
    return (
      <section aria-label="Automatic insights" className="card">
        <h2 className="text-sm font-semibold text-ink-900">What the data shows</h2>
        <p className="mt-2 text-xs text-ink-500" role="status">
          Computing insights…
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Automatic insights" className="space-y-2">
      <div>
        <h2 className="text-sm font-semibold text-ink-900">What the data shows</h2>
        <p className="text-xs text-ink-500">{data.note}</p>
      </div>
      <ul className="grid gap-3 lg:grid-cols-2">
        {data.insights.map((item) => (
          <InsightCard key={item.id} item={item} />
        ))}
      </ul>
    </section>
  );
}
