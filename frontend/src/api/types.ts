/** Typed mirrors of the FastAPI response schemas (backend app/models/schemas.py). */

export type Grain = "hourly" | "halfhourly";

export interface HealthResponse {
  status: string;
  service: string;
  period_start: string;
  period_end: string;
  decision_cutoff_utc: string;
  fuel_type: string;
  cache: {
    loaded: boolean;
    loaded_at: string | null;
    age_seconds: number | null;
    ttl_seconds: number;
    refresh: string;
    endpoint_refresh_param: string;
  };
}

export interface AccuracyStats {
  grain: Grain;
  n_expected: number;
  n_matched: number;
  n_missing: number;
  coverage_pct: number;
  coverage_complete: boolean;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  mape_pct: number | null;
  mape_excluded_intervals: number;
  median_abs_error_mw: number | null;
  p90_abs_error_mw: number | null;
  n_missing_actual: number;
  n_missing_forecast: number;
  avg_forecast_mw: number | null;
  avg_actual_mw: number | null;
  status_counts: {
    matched: number;
    forecast_only: number;
    actual_only: number;
    missing_both: number;
  };
}

export interface AccuracyResponse extends AccuracyStats {
  start: string;
  end: string;
  note: string;
}

export type IntervalStatus = "matched" | "forecast_only" | "actual_only" | "missing_both";

export interface TimeseriesRow {
  timestamp: string;
  settlement_date: string;
  settlement_period: number | null;
  actual_mw: number | null;
  forecast_mw: number | null;
  error_mw: number | null;
  status: IntervalStatus;
  forecast_publish_time: string | null;
}

export interface TimeseriesResponse {
  grain: Grain;
  start: string;
  end: string;
  rows: TimeseriesRow[];
}

// -- Feature A: historical forecast vintage explorer ------------------------

export interface VintageItem {
  publish_time: string;
  forecast_mw: number | null;
  change_mw: number | null;
  eligible_at_cutoff: boolean;
  selected: boolean;
}

export interface VintageIntervalResponse {
  delivery_timestamp: string;
  settlement_date: string;
  settlement_period: number;
  clock_hour: string;
  cutoff_utc: string;
  actual_mw: number | null;
  selected_publish_time: string | null;
  selected_forecast_mw: number | null;
  error_mw: number | null;
  absolute_error_mw: number | null;
  latest_publish_time: string | null;
  latest_forecast_mw: number | null;
  eligible_count: number;
  post_cutoff_count: number;
  vintages: VintageItem[];
  limitation: string | null;
  note: string;
}

// -- Feature D: data quality and provenance ---------------------------------

export interface DataQualityResponse {
  sources: { actual: string; forecast: string };
  fuel_type: string;
  forecast_available: boolean;
  period_start: string;
  period_end: string;
  decision_cutoff_utc: string;
  expected_halfhourly_intervals: number;
  actual_records_fetched: number;
  actual_records_present: number;
  forecast_records_fetched: number;
  eligible_forecast_records: number;
  selected_forecast_records: number;
  matched_intervals: number;
  missing_actual_intervals: number;
  missing_forecast_intervals: number;
  coverage_pct: number;
  duplicate_records_dropped: { actual: number; forecast: number };
  null_values_in_source: { actual: number; forecast: number };
  cache_loaded_at: string | null;
  cache_age_seconds: number | null;
  cache_ttl_seconds: number;
  quality_status: string;
  limitations: string[];
  note: string;
}

// -- Feature E: evidence-based insights -------------------------------------

export interface InsightItem {
  id: string;
  finding: string;
  evidence: string;
  period: string;
  why_it_matters: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface InsightsResponse {
  grain: Grain;
  start: string;
  end: string;
  insights: InsightItem[];
  note: string;
}
