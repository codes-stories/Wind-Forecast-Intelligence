# Video Recording Guide — Two-Part Demo + Knowledge Transfer

Companion to [`docs/video-script.md`](video-script.md) (the minute-by-minute narration script).
**This document is the one to record from:** it carries the storyboard for both parts *and* the
code snippets, file paths and explanations you need for the Part 2 knowledge transfer.

**Spec (from the brief):** one **unlisted** YouTube video, **≤ 10:00 total**,
**Part 1 (customer) ≤ 5:00**, **Part 2 (tech-lead review / KT) ≤ 5:00**.

| | Audience | Tone | Goal |
|---|---|---|---|
| **Part 1** | Energy-utility client (business) | Pilot-project demo, plain language | Impress: the product answers their two questions with auditable numbers |
| **Part 2** | Internal technical lead | Engineer-to-engineer | Make review and **knowledge transfer** easy: architecture, design, key code, practices |

---

## 0. Pre-flight (do this before you hit record)

```bash
docker compose up --build          # dashboard http://localhost:8081
curl -s http://localhost:8000/health          # expect {"status":"ok",...}
```

- [ ] Open an **incognito** window on `http://localhost:8081`, wait for KPIs (~4–6 s first load).
- [ ] Click through all four tabs once (**Overview · Forecast Explorer · Error Analysis · Data Quality**)
      so each is warm — no loading spinners mid-sentence.
- [ ] Have these tabs/windows ready and switchable with one keystroke:
      1. dashboard · 2. `http://localhost:8000/api/overview` · 3. your editor at
         `backend/app/services/forecast_service.py` · 4. terminal for `docker compose` / tests
- [ ] Numbers you will quote (verified live — `curl /api/overview`):
      MAE **2,145 MW** (half-hourly) / **2,142** (hourly) · RMSE **2,616** · Bias **+1,852** ·
      MAPE **22.4 %** · Coverage **100 % (1,488/1,488)** · avg forecast **13.43 GW** vs
      avg actual **11.58 GW** · 256 vintages, 31 selected (always D−1 07:30 UTC).
- [ ] Screen resolution 100 %, notifications off, phone silent.
- [ ] Record Part 1 and Part 2 as **separate takes**; join in order afterwards.

---

# PART 1 — Customer presentation (≤ 5:00)

*Tone: you are a product developer handing over a pilot. No jargon, no code on screen.*

| # | Time | Screen | Say / do |
|---|---|---|---|
| 1 | 0:00–0:30 | Dashboard full page, incognito | **The problem in their words.** *"You commit to wind volumes for tomorrow before the day-ahead gate closes. You can't see the outturn yet — so you are only as good as the forecast you had. This pilot answers: which forecast did you actually have, and how wrong was it?"* One line only: it measures forecast reliability, it does **not** compute a trading position. |
| 2 | 0:30–1:15 | Header + filter bar | **Scope and provenance.** Point at: reporting period **1–31 Jan 2026**, source **Elexon BMRS** (FUELHH actual vs WINDFOR forecast), badge **decision cutoff 09:20 UTC on D−1**. Show the date range + aggregation filters. *"One month, every half-hour, real published grid data — no samples, no estimates."* |
| 3 | 1:15–2:15 | **Forecast vs actual** chart | **Requirement 1 made visible.** *"Blue is the forecast as it stood at the decision moment; amber is what actually generated."* Hover one close pair and one wide gap. *"Gaps would mean missing data — we never fill them with zero."* Then point at **What the data shows**: *"The app states its findings in plain language and each finding prints the numbers behind it."* Switch aggregation Half-hourly → Daily → back. |
| 4 | 2:15–3:15 | **KPI row** | **Requirement 2 — the numbers.** MAE ~2.1 GW *"typical miss on a fleet averaging 11.6 GW"*; RMSE ~2.6 GW *"punishes the bad days harder"*; **Bias +1.85 GW** *"forecast minus actual — we over-forecast on average by ~1.9 GW. Systematic, one-directional: the kind of error you can plan a position around."*; **Coverage 100 % (1,488/1,488)** *"not a sample — the whole month."* Do **not** claim savings or P&L. |
| 5 | 3:15–4:15 | Data table → **Forecast Explorer** | **Auditability.** Sort *Absolute error* descending, open the top row: delivery timestamp, forecast, actual, error, **Forecast published (UTC)**. Then Forecast Explorer for that interval: the evolution chart, the selected vintage badged **selected (at cutoff)**, later ones **post-cutoff, excluded**, Δ vs previous. *"Every number traces to the exact publication you would have seen before the gate closed — and you can see the revisions we deliberately don't use."* |
| 6 | 4:15–4:40 | **Data Quality** tab | **Trust.** *"Fetched vs present vs eligible vs selected, duplicates, nulls, coverage, cache age, and an explicit limitations list. The status says 'all intervals matched' — it never says 'verified'."* |
| 7 | 4:40–5:00 | Back to KPI row | **Close.** *"It turns 'we think the forecast is okay' into auditable numbers per interval."* Limitations, stated plainly: January 2026 only; WINDFOR units assumed MW (Elexon doesn't document them); reliability, not a trading position. Next: deploy, more months, scheduled refresh. **Hard stop ≤ 5:00.** |

**Part 1 rules:** no file names, no terminal, no `curl`, no framework names. If you catch
yourself saying "FastAPI" or "React", stop and rephrase as "the dashboard" / "the service".

---

# PART 2 — Technical review & knowledge transfer (≤ 5:00)

*Same person, engineer voice. Show real code and real behaviour; explain decisions, don't read files.*

### Module map (keep this mental map — it is the spine of the KT)

```
backend/app/
├── main.py                 app + CORS + ElexonError → 502 handler
├── core/config.py          Settings (env) + fuel-type validation
├── api/routes.py           all HTTP contracts (response models from schemas.py)
├── models/
│   ├── schemas.py          PUBLIC response shapes (source of truth)
│   └── records.py          internal dataclasses + classify()
└── services/
    ├── elexon_client.py    HTTP, retries, filters, error taxonomy
    ├── forecast_service.py dedupe → cutoff selection → alignment → cache → vintages
    ├── metrics_service.py  MAE/RMSE/bias/MAPE/median/p90 over matched intervals
    └── insights_service.py deterministic findings (no LLM)

frontend/src/
├── App.tsx                 state, filters, tabs, fetch orchestration
├── api/client.ts           typed fetch + ApiError + AbortSignal
├── api/types.ts            MIRROR of schemas.py (compile-time contract)
├── components/*.tsx        Header, KpiCards, charts, DataTable, Explorer, Heatmap…
└── lib/{aggregate,heatmap}.ts   pure, unit-tested transformations
```

---

### 2.1 Architecture and the "why" (0:00–0:40)

**Screen:** the ASCII diagram from `README.md` §5 (or draw it live).

**Say:** *"FastAPI + Pydantic backend, React/TypeScript/Vite frontend, Recharts for visuals.
Two containers behind nginx; no database."*

**The design decision to state out loud:**
> *"Why no DB? The whole study period is ~1,488 actual rows plus ~18,688 forecast rows. That
> fits in memory, so a cache-invalidation problem would be more complexity than the pilot is
> worth. The dataset is loaded lazily on the first request and cached with a 1-hour TTL."*

---

### 2.2 Data acquisition — `backend/app/services/elexon_client.py` (0:40–1:25)

**Show `elexon_client.py:123` — `fetch_actuals`:**

```python
def fetch_actuals(self, start: date, end: date, fuel_type: str | None = None) -> list[ActualRow]:
    fuel = normalize_fuel_type(fuel_type or self.settings.fuel_type)
    payload = self._get(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": start.isoformat(),
            "settlementDateTo":   end.isoformat(),
            "fuelType": fuel,          # server-side filter, re-checked client-side below
        },
    )
```

**Explain:**
- FUELHH (half-hourly actual) takes **settlement-date** filters; WINDFOR (hourly forecast) takes
  **publish-time** filters — they are *mutually exclusive* upstream. Mixing them returns HTTP 400.
  We hit that during discovery and encoded it, see `docs/api_findings.md:88`.
- The `fuelType` value is validated **before** the request
  (`app/core/config.py:39 normalize_fuel_type`), because upstream answers an unknown fuel with
  **HTTP 200 + `[]`** — which would silently serve an empty dashboard. This is the kind of
  upstream quirk the client layer owns.

**Show `elexon_client.py:81` — `_get` (retry policy):**

```python
def _get(self, path: str, params: dict) -> object:
    last_error: Exception | None = None
    for attempt in range(1, self.settings.http_retries + 1):
        try:
            with httpx.Client(timeout=self.settings.http_timeout_seconds) as client:
                response = client.get(url, params=params)
        except httpx.TimeoutException as exc:
            last_error = ElexonTransportError(f"timeout calling {path}")
            time.sleep(0.3 * attempt); continue          # linear backoff
        ...
        if response.status_code in RETRYABLE_STATUS:     # 429/500/502/503/504
            ... time.sleep(0.3 * attempt); continue
        if response.status_code >= 400:
            raise ElexonHTTPError(response.status_code, response.text)   # 4xx: never retried
```

**Explain the error taxonomy** — three exception types, one HTTP mapping:

| Exception | Meaning | Surfaced as |
|---|---|---|
| `ElexonTransportError` | timeout / connection failure after retries | 502 |
| `ElexonHTTPError` | upstream 4xx/5xx (4xx not retried) | 502 with the real body |
| `ElexonSchemaError` | malformed JSON / missing required field | 502 |

Handler: **`backend/app/main.py:40`**

```python
@app.exception_handler(ElexonError)
async def elexon_error_handler(request: Request, exc: ElexonError) -> JSONResponse:
    """Any upstream Elexon failure surfaces as 502 with the real error text."""
    return JSONResponse(status_code=502, content=ErrorDetail(detail=str(exc)).model_dump())
```

**Key line to say:** *"One place converts upstream failure into a user-readable error; routes
never catch httpx exceptions."*

---

### 2.3 The core domain rule — `backend/app/services/forecast_service.py` (1:25–2:15)

**This is the most important 20 seconds of the KT.** Show `forecast_service.py:52` and `:58`:

```python
def decision_cutoff_for(interval_start: datetime, cutoff: time) -> datetime:
    """Decision moment for a delivery interval: cutoff time on the previous day."""
    day = interval_start.date() - timedelta(days=1)
    return datetime.combine(day, cutoff, tzinfo=timezone.utc)


def select_decision_time_forecasts(rows, cutoff, period_start, period_end) -> dict[datetime, ForecastRow]:
    """Latest eligible forecast per delivery hour (publishTime preserved)."""
    best: dict[datetime, ForecastRow] = {}
    for row in rows:
        if row.start_time.date() < period_start or row.start_time.date() > period_end:
            continue
        if row.publish_time > decision_cutoff_for(row.start_time, cutoff):
            continue                                   # post-cutoff: never eligible
        current = best.get(row.start_time)
        if current is None or row.publish_time > current.publish_time:
            best[row.start_time] = row                 # latest eligible wins
    return best
```

**Explain:**
1. *Point-in-time*: for delivery hour *T* on day *D*, only vintages with
   `publishTime ≤ (D−1 09:20 UTC)` are eligible; among them the **latest publishTime wins**.
2. *We select, we never rewrite* — Elexon's original `publishTime` is carried through to the UI
   and the CSV, so every number is traceable.
3. **Result for Jan 2026:** exactly one vintage per day — **D−1 07:30 UTC** for all 31 days;
   audited **0 cutoff violations across 1,488 intervals**.
4. `/api/forecasts/latest` also returns `ignored_post_cutoff_publish_times` so a reviewer can
   see what was excluded.

**Then show the enforcement test** — `backend/tests/test_forecast_selection.py:31`:

```python
def test_cutoff_wins_over_newer_value():
    """A better-looking post-cutoff forecast must never be selected."""
    delivery = dt(15, 10)
    eligible = make_forecast(dt(14, 7, 30), delivery, 5000)
    post     = make_forecast(dt(14, 9, 30), delivery, 9999)   # 09:30 > 09:20
    chosen = select([eligible, post])
    assert chosen[delivery].generation_mw == 5000
```

**Key line:** *"The business rule lives in a pure function and the test states the rule in
English. That is what makes it reviewable."*

---

### 2.4 Alignment of two different grains (2:15–2:45)

Show **`forecast_service.py:141` — `build_halfhourly_points`:**

```python
for period in range(1, 49):
    ts = base + timedelta(minutes=30 * (period - 1))
    forecast = selected.get(ts.replace(minute=0))   # hourly forecast → both half-hours
    actual_row = actual_by_start.get(ts)            # native half-hourly actual
    actual = actual_row.generation_mw if actual_row else None      # None, never 0
    points.append(IntervalPoint(...,
        status=classify(forecast_mw is not None, actual is not None),
        forecast_publish_time=forecast.publish_time if forecast else None))
```

**Explain the three grain rules** (also `README.md` §8):

| Grain | Actual | Forecast |
|---|---|---|
| half-hourly (native) | FUELHH value for that period | the hourly value mapped to **both** half-hours |
| hourly | mean of the **two** half-hours — *both required* | the hourly value |
| daily | mean of complete days only | same |

- Missing → `status` from `classify()` in **`models/records.py:52`**
  (`matched` / `forecast_only` / `actual_only` / `missing_both`), `actual_mw = None`.
  **No interpolation, no zero-fill** anywhere — charts show gaps, CSV writes empty fields.
- Every `IntervalPoint` carries `forecast_publish_time`, which is what the UI's
  "Forecast published (UTC)" column renders.

---

### 2.5 Metrics — `backend/app/services/metrics_service.py:57` (2:45–3:15)

```python
def compute_stats(points, expected_count, grain) -> AccuracyStats:
    matched = [p for p in points if p.status == STATUS_MATCHED
               and p.actual_mw is not None and p.forecast_mw is not None]
    coverage = (100.0 * n_matched / n_expected) if n_expected else 0.0

    errors   = [p.forecast_mw - p.actual_mw for p in matched]   # F − A
    mae      = _mean([abs(e) for e in errors])
    rmse     = math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None
    bias     = _mean(errors)                                    # + = over-forecast
    p90_abs  = _p90_nearest_rank(abs_errors) if n_matched >= P90_MIN_MATCHED else None
    pct_errors = [abs(f - a) / abs(a) for ... if p.actual_mw != 0]   # MAPE skips A = 0
    mape_excluded = n_matched - len(pct_errors)                 # reported, never hidden
```

**Say:**
- **Matched intervals only**, and `coverage` is returned in the *same* payload — you can never
  get a MAE without seeing how much data it covers.
- **Bias = mean(F − A)** → positive = over-forecast (our January: **+1,852 MW**).
- MAPE excludes actual = 0 and reports `mape_excluded_intervals`.
- No matched intervals → metric is `None` (JSON `null`), **never 0**.
- p90 uses **nearest-rank** and is suppressed below 10 matched intervals; it is labelled a
  *historical statistic*, not a confidence bound.

**Say:** *"An independent audit script recomputed every metric straight from
`/api/timeseries` and matched the API to 3 decimals."*

---

### 2.6 API layer and the contract (3:15–3:40)

**Show `backend/app/api/routes.py:57`:**

```python
def get_store_dep(
    refresh: bool = Query(False, description="Force a reload of the cached dataset"),
    fuel_type: Optional[str] = Query(None, description="FUELHH fuel filter ..."),
) -> DataStore:
    settings = get_settings()
    return forecast_service.get_store(
        settings, refresh=refresh, fuel_type=_fuel_type(fuel_type, settings)
    )
```

**Explain:**
- **FastAPI dependency injection**: every data endpoint declares
  `store: DataStore = Depends(get_store_dep)`, so caching, the `refresh` flag and fuel
  validation are decided **once** and inherited by `/api/overview`, `/api/timeseries`,
  `/api/accuracy`, `/api/insights`, `/api/data-quality`, `/api/export.csv`.
- Input validation is centralized (`routes.py:75 _validate_range`) → **400** with a
  machine-readable `detail`; FastAPI gives **422** for malformed query/date types.
- `routes.py:49 _fuel_type` rejects unknown fuels with **400** instead of letting upstream
  return an empty dataset.

**Show the contract mirror** — `backend/app/models/schemas.py` vs `frontend/src/api/types.ts`:

```python
# backend/app/models/schemas.py
class AccuracyStats(BaseModel):
    grain: Grain
    n_expected: int = Field(description="Delivery intervals expected in the requested range")
    mae_mw: Optional[float]
    bias_mw: Optional[float] = Field(None, description="Mean signed error = forecast - actual")
```

```typescript
// frontend/src/api/types.ts — typed mirror, must stay in sync by review
export interface AccuracyStats {
  grain: Grain;
  n_expected: number;
  mae_mw: number | null;
  bias_mw: number | null;
  ...
}
```

**Say:** *"Pydantic schema is the single source of truth for response shapes; `types.ts` mirrors
it, `App.test.tsx` fixtures are typed against it — so a shape change fails `tsc` or the tests."*
Also mention: `schemas.py` carries the human descriptions, which FastAPI emits straight into
`/docs` (Swagger) — the API is self-documenting.

**Cache, one slide** — `forecast_service.py:323`:

```python
def get_store(settings, refresh: bool = False, fuel_type: str | None = None) -> DataStore:
    fuel = normalize_fuel_type(fuel_type or settings.fuel_type)
    with _lock:                                   # thread-safe, one loader at a time
        store = _stores.get(fuel)                 # one store per fuel type
        stale = store is None or not store.is_loaded or age > settings.cache_ttl_seconds
        if refresh or stale:
            store = build_store(settings, fuel)
            store.load()                          # ElexonError → 502 handler
            _stores[fuel] = store
        return store
```

*"In-process, keyed by fuel, TTL 3600 s, `?refresh=true` forces a reload. Deliberately simple:
a restart re-fetches, and that is an acceptable trade-off for a pilot with no persistence."*

---

### 2.7 Frontend — `frontend/src/api/client.ts` + `App.tsx` (3:40–4:10)

**Show `client.ts:33 getJson`:**

```ts
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Backend unreachable — start the API server and retry.");
  }
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  return (await response.json()) as T;
}
```

**Say:** one generic fetch wrapper → every call is typed, non-2xx becomes an `ApiError`
carrying the backend's `detail` string, and network failure is a *different*, human message
than a 5xx. `BASE = import.meta.env.VITE_API_BASE ?? ""` is the **one** place a deployment
differs (same-origin proxy vs split-host CORS).

**Show `App.tsx:59` — the data effect:**

```ts
const controller = new AbortController();
setLoading(true); setError(null);
Promise.all([
  api.accuracy({ start, end, grain: accuracyGrain }, controller.signal),
  api.timeseries({ start, end, grain: "halfhourly" }, controller.signal),
]).then(([nextAccuracy, nextTimeseries]) => { ... })
  .catch((err) => { if (err.name === "AbortError") return; setError(...); });
return () => controller.abort();        // cancel in-flight requests on filter change
```

**Say:** *"State is local `useState`; every filter change cancels the previous request, so a slow
response can never overwrite a newer one. The timeseries is always fetched at the native
half-hourly grain and daily/hourly views are derived client-side in
`lib/aggregate.ts` — the client **transforms, it never recomputes metrics**.
All math (MAE/RMSE/bias/MAPE/p90/insights) lives in Python."*

Also worth one sentence each:
- `lib/heatmap.ts:44 buildHeatmap` — pure, separately unit-tested; missing cells are hatched,
  distinct from a genuine `0`.
- Components fetch only what they own (`ForecastExplorer`, `Insights`, `DataQualityPanel` each
  call their own endpoint via `useEffect`).

---

### 2.8 Testing and engineering practices (4:10–4:35)

**Run both suites on camera:**

```bash
cd backend  && ../.venv/bin/python -m pytest -q     # 88 passed
cd frontend && npm test                             # 40 passed (+1 gated)
```

**Say what the tests protect** (this is the KT part, not the number):

| Practice | Evidence |
|---|---|
| Business rules as tests | `tests/test_forecast_selection.py` — post-cutoff never wins, same-day vintage excluded |
| API contract tests | `tests/test_api.py` — response shapes, 400/422 validation, 502 propagation, CORS allow-list |
| Upstream fault injection | `tests/test_elexon_client.py` — `httpx.MockTransport` simulates 400/429/500/timeout/malformed JSON |
| No zero-fill proven | `test_features.py::test_export_csv_missing_values_are_empty_not_zero` |
| Upstream verified, not assumed | `scripts/verify_api.py` — 30+ live checks (schema, cadence, 48 SP/day, cutoff rule) |
| Frontend | Vitest + Testing Library; `LIVE=1 npm test` runs a real integration test against a running backend |
| Types | `npm run build` runs `tsc --noEmit` first; schemas mirrored in `types.ts` |
| Determinism | `insights_service.py` is pure Python — **no LLM**, every insight carries its evidence |

**Also mention:** development used **opencode** (AI coding agent) under continuous human
direction, disclosed in `README.md` §18; AI output was reviewed, tested and audited before
acceptance.

---

### 2.9 Docker, deployment, limitations (4:35–5:00)

**Show `docker-compose.yml` + `frontend/nginx.conf.template:9`:**

```yaml
# docker-compose.yml — the frontend waits for a healthy backend
frontend:
  depends_on:
    backend:
      condition: service_healthy        # healthcheck hits /health
```

```nginx
# frontend/nginx.conf.template — same-origin API proxy (no CORS in Docker)
location /api/   { proxy_pass ${BACKEND_URL}; ... }
location = /health { proxy_pass ${BACKEND_URL}/health; }
location /       { try_files $uri $uri/ /index.html; }   # SPA fallback
```

**Say:** *"Two deployment modes. Docker/nginx: browser stays same-origin, the proxy forwards
`/api` and `/health`, so CORS never enters the picture. Split-host (Vercel static frontend +
long-running backend): `VITE_API_BASE` at build time points at the API and
`ALLOWED_ORIGINS` on the backend permits it — CORS is restricted to an explicit list, not `*`."*

**Deployment status — be honest and brief:** frontend target **Vercel**, backend target
**Render** (`render.yaml` blueprint). Heroku was evaluated but has no free tier (card + paid
dyno). **Not deployed: platform credentials were not available**, so there is no live URL;
the steps are in `README.md` §17.

**Close on limitations + next steps (15 s):** WINDFOR units assumed MW (undocumented upstream);
in-memory cache dies with the process; free hosts sleep when idle; single month; next =
persistence (SQLite/Parquet), scheduled refresh, multi-month range, CI (pytest + vitest +
docker build).

**Last frame:** `git log --oneline` and the two test counts. **Hard stop ≤ 5:00.**

---

## Timing budget

| | Target | Hard cap | If you run over, cut… |
|---|---|---|---|
| Part 1 | ~4:30 | **5:00** | Step 6 (Data Quality) — fold one sentence into step 5 |
| Part 2 | ~4:30 | **5:00** | 2.2 retry internals (keep the error-taxonomy table) → then 2.6 cache slide |
| **Combined** | **~9:00** | **10:00** | — |

---

## After recording

- [ ] Upload as **Unlisted** (never Public); set the title before sharing.
- [ ] Check the duration in YouTube Studio: each part ≤ 5:00, total ≤ 10:00.
- [ ] Watch once with sound off — every on-screen number must match the running app.
- [ ] Run the incognito pass on: GitHub repo · README · screenshots · (deployed URLs once live)
      — see [`docs/submission-checklist.md`](submission-checklist.md).
- [ ] Paste the video URL + repo URL + deployment URLs into the submission form.
- [ ] Keep `docs/video-script.md` alongside: it has the fuller narration wording if a take
      needs a retake.
