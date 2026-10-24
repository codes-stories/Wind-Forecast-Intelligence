import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api/client";
import type { AccuracyResponse, HealthResponse, TimeseriesRow } from "./api/types";
import FilterBar from "./components/FilterBar";
import type { Aggregation } from "./components/FilterBar";
import DataTable from "./components/DataTable";
import ErrorAnalysis from "./components/ErrorAnalysis";
import ForecastActualChart from "./components/ForecastActualChart";
import Header from "./components/Header";
import KpiCards from "./components/KpiCards";
import { EmptyState, ErrorPanel, LoadingState } from "./components/States";
import { toDailyPoints, toHalfhourlyPoints } from "./lib/aggregate";

const DEFAULT_START = "2026-01-01";
const DEFAULT_END = "2026-01-31";

interface Filters {
  start: string;
  end: string;
  aggregation: Aggregation;
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [filters, setFilters] = useState<Filters>({
    start: DEFAULT_START,
    end: DEFAULT_END,
    aggregation: "halfhourly",
  });
  const [accuracy, setAccuracy] = useState<AccuracyResponse | null>(null);
  const [rows, setRows] = useState<TimeseriesRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then(setHealth)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        // health is optional context; data endpoints surface their own errors
        setHealth(null);
      });
    return () => controller.abort();
  }, []);

  const rangeInvalid = filters.start > filters.end;

  useEffect(() => {
    if (rangeInvalid) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    // timeseries: always half-hourly rows (native delivery grain) —
    // daily series is derived from them in toDailyPoints().
    const accuracyGrain = filters.aggregation === "daily" ? "hourly" : "halfhourly";
    Promise.all([
      api.accuracy({ start: filters.start, end: filters.end, grain: accuracyGrain }, controller.signal),
      api.timeseries({ start: filters.start, end: filters.end, grain: "halfhourly" }, controller.signal),
    ])
      .then(([nextAccuracy, nextTimeseries]) => {
        setAccuracy(nextAccuracy);
        setRows(nextTimeseries.rows);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error");
        setLoading(false);
      });
    return () => controller.abort();
  }, [filters, attempt, rangeInvalid]);

  const points = useMemo(() => {
    if (!rows) return [];
    return filters.aggregation === "daily" ? toDailyPoints(rows) : toHalfhourlyPoints(rows);
  }, [rows, filters.aggregation]);

  const updateFilters = useCallback((next: Partial<Filters>) => {
    setFilters((prev) => ({ ...prev, ...next }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({ start: DEFAULT_START, end: DEFAULT_END, aggregation: "halfhourly" });
  }, []);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  const minDate = health?.period_start ?? DEFAULT_START;
  const maxDate = health?.period_end ?? DEFAULT_END;

  return (
    <div className="min-h-screen">
      <Header health={health} />
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6">
        <FilterBar
          start={filters.start}
          end={filters.end}
          aggregation={filters.aggregation}
          minDate={minDate}
          maxDate={maxDate}
          onChange={updateFilters}
          onReset={resetFilters}
        />

        {error && <ErrorPanel message={error} onRetry={retry} />}

        {!error && loading && !accuracy && <LoadingState />}

        {!error && rangeInvalid && (
          <EmptyState message="Fix the date range to load the analysis." />
        )}

        {!error && !rangeInvalid && accuracy && (
          <>
            <KpiCards stats={accuracy} loading={loading} />
            <p className="text-xs text-ink-500">
              Metrics computed by the backend over {accuracy.n_expected} {accuracy.grain} intervals in
              range ({accuracy.n_matched} matched, coverage {accuracy.coverage_pct.toFixed(1)}%) ·{" "}
              {accuracy.note}
            </p>
          </>
        )}

        {!error && !rangeInvalid && !loading && points.length === 0 && rows && (
          <EmptyState message="No delivery intervals returned for the selected range." />
        )}

        {!error && !rangeInvalid && points.length > 0 && (
          <>
            <ForecastActualChart points={points} aggregation={filters.aggregation} />
            <ErrorAnalysis points={points} aggregation={filters.aggregation} />
            <DataTable points={points} daily={filters.aggregation === "daily"} />
          </>
        )}

        {!error && !rangeInvalid && loading && points.length > 0 && (
          <LoadingState label="Updating analysis…" />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs leading-relaxed text-ink-500 sm:px-6">
        <p>
          <strong className="font-semibold text-ink-700">Wind Forecast Intelligence</strong> —
          retrospective day-ahead UK wind forecast evaluation for January 2026. Actuals: Elexon BMRS
          FUELHH (fuelType=WIND, half-hourly, average MW). Forecasts: Elexon BMRS WINDFOR (hourly
          vintages, MW assumed — see docs/api_findings.md). Forecast vintage selected per delivery
          interval: the latest published at or before the historical decision cutoff (09:20 UTC on
          D-1); post-cutoff publications are never used. Hourly forecasts are mapped to both
          half-hours of their clock hour in the half-hourly view; daily values are means of complete
          days only. All timestamps UTC. Missing values are shown as gaps or “—”, never as zero.
        </p>
      </footer>
    </div>
  );
}
