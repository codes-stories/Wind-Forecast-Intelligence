/** Typed mirrors of the FastAPI response schemas (backend app/models/schemas.py). */

export type Grain = "hourly" | "halfhourly";

export interface HealthResponse {
  status: string;
  service: string;
  period_start: string;
  period_end: string;
  decision_cutoff_utc: string;
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
