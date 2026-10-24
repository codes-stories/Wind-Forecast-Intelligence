/** Minimal typed fetch client for the Wind Forecast Intelligence API. */
import type {
  AccuracyResponse,
  DataQualityResponse,
  HealthResponse,
  InsightsResponse,
  TimeseriesResponse,
  VintageIntervalResponse,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE: string = import.meta.env.VITE_API_BASE ?? "";

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* body was not JSON */
  }
  return `Request failed with status ${response.status}`;
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Backend unreachable — start the API server and retry.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  return (await response.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => getJson<HealthResponse>("/health", signal),
  accuracy: (params: { start: string; end: string; grain: string }, signal?: AbortSignal) =>
    getJson<AccuracyResponse>(
      `/api/accuracy?start=${params.start}&end=${params.end}&grain=${params.grain}`,
      signal,
    ),
  timeseries: (params: { start: string; end: string; grain: string }, signal?: AbortSignal) =>
    getJson<TimeseriesResponse>(
      `/api/timeseries?start=${params.start}&end=${params.end}&grain=${params.grain}`,
      signal,
    ),
  vintages: (params: { date: string; period: number }, signal?: AbortSignal) =>
    getJson<VintageIntervalResponse>(
      `/api/forecasts/vintages?date=${params.date}&period=${params.period}`,
      signal,
    ),
  dataQuality: (signal?: AbortSignal) => getJson<DataQualityResponse>("/api/data-quality", signal),
  insights: (params: { start: string; end: string; grain: string }, signal?: AbortSignal) =>
    getJson<InsightsResponse>(
      `/api/insights?start=${params.start}&end=${params.end}&grain=${params.grain}`,
      signal,
    ),
};

/** CSV download URL for the current filters (Feature F - same rows as /api/timeseries). */
export function exportCsvUrl(params: { start: string; end: string; grain: string }): string {
  return `${BASE}/api/export.csv?start=${params.start}&end=${params.end}&grain=${params.grain}`;
}
