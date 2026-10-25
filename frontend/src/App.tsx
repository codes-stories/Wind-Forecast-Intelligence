import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api/client";
import type { AccuracyResponse, HealthResponse, TimeseriesRow } from "./api/types";
import CostPanel from "./components/CostPanel";
import DataQualityPanel from "./components/DataQualityPanel";
import DecisionLab from "./components/DecisionLab";
import FilterBar from "./components/FilterBar";
import type { Aggregation } from "./components/FilterBar";
import DataTable from "./components/DataTable";
import ErrorAnalysis from "./components/ErrorAnalysis";
import ForecastActualChart from "./components/ForecastActualChart";
import ForecastExplorer from "./components/ForecastExplorer";
import Header from "./components/Header";
import Heatmap from "./components/Heatmap";
import Insights from "./components/Insights";
import KpiCards from "./components/KpiCards";
import ReliabilityPanel from "./components/ReliabilityPanel";
import { EmptyState, ErrorPanel, LoadingState } from "./components/States";
import TabNav from "./components/TabNav";
import type { View } from "./components/TabNav";
import { toDailyPoints, toHalfhourlyPoints } from "./lib/aggregate";

const DEFAULT_START = "2026-01-01";
const DEFAULT_END = "2026-01-31";
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const VALID_TABS: View[] = ["overview", "explorer", "errors", "lab", "quality"];

interface Filters {
  start: string;
  end: string;
  aggregation: Aggregation;
}

/** Deep links: ?start=&end=&agg=&tab= reopen an exact view (see Copy view link). */
function readInitialState(): { filters: Filters; view: View } {
  const params = new URLSearchParams(window.location.search);
  const start = params.get("start");
  const end = params.get("end");
  const agg = params.get("agg");
  const tab = params.get("tab") as View | null;
  return {
    filters: {
      start: start && DATE_PATTERN.test(start) ? start : DEFAULT_START,
      end: end && DATE_PATTERN.test(end) ? end : DEFAULT_END,
      aggregation: agg === "daily" ? "daily" : "halfhourly",
    },
    view: tab && VALID_TABS.includes(tab) ? tab : "overview",
  };
}

export default function App() {
  const initial = useMemo(readInitialState, []);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [view, setView] = useState<View>(initial.view);
  const [filters, setFilters] = useState<Filters>(initial.filters);
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

  // Keep the address bar in sync so the current view is always shareable.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("start", filters.start);
    params.set("end", filters.end);
    params.set("agg", filters.aggregation);
    params.set("tab", view);
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}`,
    );
  }, [filters, view]);

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
  const accuracyGrain = filters.aggregation === "daily" ? "hourly" : "halfhourly";
  const showFilters = view === "overview" || view === "errors" || view === "lab";
  const rangeReady = !error && !rangeInvalid;

  return (
    <div className="min-h-screen">
      <Header health={health} />
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6">
        <TabNav view={view} onChange={setView} />

        {showFilters && (
          <FilterBar
            start={filters.start}
            end={filters.end}
            aggregation={filters.aggregation}
            minDate={minDate}
            maxDate={maxDate}
            onChange={updateFilters}
            onReset={resetFilters}
          />
        )}

        {error && <ErrorPanel message={error} onRetry={retry} />}

        {rangeInvalid && showFilters && (
          <EmptyState message="Fix the date range to load the analysis." />
        )}

        {view === "overview" && rangeReady && (
          <>
            {accuracy ? (
              <>
                <KpiCards stats={accuracy} loading={loading} />
                <p className="text-xs text-ink-500">
                  Metrics computed by the backend over {accuracy.n_expected} {accuracy.grain} intervals in
                  range ({accuracy.n_matched} matched, coverage {accuracy.coverage_pct.toFixed(1)}%) ·{" "}
                  {accuracy.note}
                </p>
              </>
            ) : (
              loading && <LoadingState />
            )}

            {accuracy && rows && rows.length > 0 && <CostPanel rows={rows} stats={accuracy} />}

            {points.length === 0 && rows && !loading && (
              <EmptyState message="No delivery intervals returned for the selected range." />
            )}

            {points.length > 0 && <ForecastActualChart points={points} aggregation={filters.aggregation} />}

            {accuracy && (
              <Insights start={filters.start} end={filters.end} grain={accuracyGrain} />
            )}

            {points.length > 0 && <DataTable points={points} daily={filters.aggregation === "daily"} />}

            {loading && points.length > 0 && <LoadingState label="Updating analysis…" />}
          </>
        )}

        {view === "explorer" && !error && (
          <ForecastExplorer minDate={minDate} maxDate={maxDate} defaultDate={filters.start} />
        )}

        {view === "errors" && rangeReady && (
          <>
            {points.length > 0 && <ErrorAnalysis points={points} aggregation={filters.aggregation} />}
            {rows && rows.length > 0 && <Heatmap rows={rows} />}
            {accuracy ? (
              <ReliabilityPanel stats={accuracy} />
            ) : (
              loading && <LoadingState label="Loading reliability metrics…" />
            )}
            {points.length === 0 && rows && !loading && (
              <EmptyState message="No delivery intervals returned for the selected range." />
            )}
          </>
        )}

        {view === "lab" && rangeReady && (
          <DecisionLab start={filters.start} end={filters.end} />
        )}

        {view === "quality" && !error && <DataQualityPanel />}
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
