/** Feature D - Data quality & provenance panel.
 * Every number is served by GET /api/data-quality; nothing is recomputed
 * client-side. Status is neutral: "incomplete" is reported, never "verified". */
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { DataQualityResponse } from "../api/types";
import { ErrorPanel, LoadingState } from "./States";

function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  return `${(seconds / 3600).toFixed(1)} h ago`;
}

function Field({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export default function DataQualityPanel() {
  const [data, setData] = useState<DataQualityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    api
      .dataQuality(signal)
      .then((next) => {
        setData(next);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, attempt]);

  if (error) return <ErrorPanel message={error} onRetry={() => setAttempt((a) => a + 1)} />;
  if (loading && !data) return <LoadingState label="Loading data quality report…" />;
  if (!data) return null;

  const complete = data.quality_status === "complete";

  return (
    <div className="space-y-4">
      <section aria-label="Dataset status" className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">Dataset status</h2>
            <p className="text-xs text-ink-500">
              {data.sources.actual} · {data.sources.forecast} · period {data.period_start} to{" "}
              {data.period_end} · decision cutoff {data.decision_cutoff_utc} UTC on D−1
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={
                complete
                  ? "badge bg-ink-100 text-ink-700"
                  : "badge bg-amberish-500/10 text-amberish-600"
              }
            >
              {complete ? "all intervals matched" : "incomplete coverage"}
            </span>
            <button type="button" className="btn" onClick={() => setAttempt((a) => a + 1)}>
              Refresh
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-ink-500">{data.note}</p>
      </section>

      <section aria-label="Completeness counts" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Field
          label="Expected intervals"
          value={String(data.expected_halfhourly_intervals)}
          hint="Half-hourly delivery intervals in the period (31 × 48)"
        />
        <Field
          label="Matched intervals"
          value={String(data.matched_intervals)}
          hint={`Coverage ${data.coverage_pct.toFixed(1)}%`}
        />
        <Field
          label="Missing actual"
          value={String(data.missing_actual_intervals)}
          hint="Forecast present, no outturn retrieved"
        />
        <Field
          label="Missing forecast"
          value={String(data.missing_forecast_intervals)}
          hint="Actual present, no eligible publication"
        />
      </section>

      <section aria-label="Source record counts" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Field
          label="Actual records fetched"
          value={String(data.actual_records_fetched)}
          hint={`${data.actual_records_present} with a generation value after dedupe`}
        />
        <Field
          label="Forecast records fetched"
          value={String(data.forecast_records_fetched)}
          hint="WINDFOR rows retrieved across all vintages"
        />
        <Field
          label="Eligible forecast records"
          value={String(data.eligible_forecast_records)}
          hint="Rows published at or before the cutoff for in-period hours"
        />
        <Field
          label="Selected forecast records"
          value={String(data.selected_forecast_records)}
          hint="One decision-time winner per delivery hour"
        />
        <Field
          label="Duplicates dropped"
          value={`A ${data.duplicate_records_dropped.actual} · F ${data.duplicate_records_dropped.forecast}`}
          hint="Deduped on (settlement interval) / (publishTime, startTime)"
        />
        <Field
          label="Null values in source"
          value={`A ${data.null_values_in_source.actual} · F ${data.null_values_in_source.forecast}`}
          hint="Nulls kept as missing, never zero-filled"
        />
        <Field
          label="Cache loaded at"
          value={data.cache_loaded_at ? `${formatAge(data.cache_age_seconds)}` : "not loaded"}
          hint={data.cache_loaded_at ? `UTC ${data.cache_loaded_at.replace(".000", "")} · TTL ${Math.round(data.cache_ttl_seconds / 60)} min` : "—"}
        />
        <Field
          label="Source"
          value="Elexon BMRS"
          hint="FUELHH + WINDFOR, no API key, fetched server-side"
        />
      </section>

      <section aria-label="Known limitations" className="card">
        <h2 className="text-sm font-semibold text-ink-900">Known limitations</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-ink-600">
          {data.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
