# How to Use — Wind Forecast Intelligence

A practical guide to running the app and getting an answer out of it. For the underlying
methodology and verified data contract see [`README.md`](README.md) and
[`docs/api_findings.md`](docs/api_findings.md).

**What it does, in one line:** for every half-hour of the delivery period, show the wind
forecast that was *actually available at the day-ahead decision moment*, and quantify how wrong
it turned out to be.

---

## 1. Run it

Three options — pick one. All three serve the same dashboard.

### Option A — Docker Compose (recommended)

```bash
docker compose up --build
# Dashboard (nginx + API proxy): http://localhost:8081
# Backend direct:                 http://localhost:8000/health
```

Open <http://localhost:8081>. First data load takes ~4–6 s (the backend fetches January 2026
from Elexon once, then caches it for 1 h).

### Option B — local dev servers (no Docker)

```bash
# terminal 1 — backend on :8000
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

# terminal 2 — frontend on :5173 (proxies /api and /health to :8000)
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>.

### Option C — just the API

```bash
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

### Health check before you start

```bash
curl -s http://127.0.0.1:8000/health
```

Expect `"status": "ok"`, the reporting period, the decision cutoff, and cache state.
This endpoint never calls upstream, so it is instant even before data is loaded.

---

## 2. The five-minute tour

| Area | What you are looking at |
|---|---|
| **Header** | Reporting period (1–31 Jan 2026), data source (Elexon BMRS), decision cutoff badge (09:20 UTC on D−1), dark/light toggle |
| **Tabs** | Overview · Forecast Explorer · Error Analysis · Data Quality |
| **Filter bar** | Date range + aggregation (Half-hourly / Hourly / Daily) + Reset — drives charts, KPIs and table together |
| **KPI row** | MAE, RMSE, Bias, MAPE, Coverage, Avg forecast vs actual — each with its matched-interval count |
| **Chart** | Blue = decision-time forecast, amber = actual outturn, gaps = missing data (never zero-filled) |
| **Insights** | "What the data shows" — 3–6 findings, each printing the exact numbers behind it |
| **Data table** | Delivery timestamp, forecast, actual, signed/absolute error, forecast publish time, status — sortable and paginated |

---

## 3. Four things you can do with it

### Task 1 — "Which forecast did I actually have when I decided?"

1. Open the **Forecast Explorer** tab.
2. Pick the delivery **date** and **period** (1–48, where 1 = 00:00–00:30 UTC).
3. Read the evolution chart: every WINDFOR publication covering that interval, chronological,
   with Δ vs the previous publication.
4. Badges tell you what matters:
   - **selected (at cutoff)** — the vintage that drives all evaluation; this is the one you had.
   - **post-cutoff, excluded** — published *after* the gate closed. Shown for context, never used.
5. The card row shows the selected forecast, the actual outturn and the resulting error.

Programmatic equivalent:

```bash
# latest eligible vintage for a delivery day + the post-cutoff ones that were ignored
curl -s "http://127.0.0.1:8000/api/forecasts/latest?delivery_date=2026-01-15"

# every publication covering one half-hour (period 25 = 12:00–12:30 UTC)
curl -s "http://127.0.0.1:8000/api/forecasts/vintages?date=2026-01-15&period=25"
```

### Task 2 — "How accurate was it, quantitatively?"

1. Stay on **Overview**, set the date range and aggregation.
2. Read the KPIs (definitions in §4 below). Key habits:
   - Always read a metric **next to its coverage** — a MAE on 60 % coverage is not a month's MAE.
   - **Bias** tells you the direction: positive = over-forecast = you bought too much wind.
3. Switch aggregation to **Daily** to see whether error concentrates on particular days.

```bash
curl -s "http://127.0.0.1:8000/api/accuracy?start=2026-01-01&end=2026-01-31&grain=halfhourly"
```

### Task 3 — "Where and when does it go wrong?"

1. Open the **Error Analysis** tab.
2. **Heatmap**: 48 settlement periods (rows) × delivery days (columns). Toggle signed vs
   absolute. Amber = over-forecast, blue = under-forecast, hatched = missing (not zero).
3. **Reliability indicators**: median |error|, 90th-percentile |error|, RMSE−MAE gap, and the
   explicit missing-actual / missing-forecast counts. Each has a plain-language tooltip.
4. Back on **Overview**, sort the **Historical delivery data** table by *Absolute error*
   descending to find the worst individual intervals.

### Task 4 — "Can I trust these numbers?"

1. Open the **Data Quality** tab.
2. It reports: records fetched vs present vs eligible vs selected, duplicates and nulls
   dropped, matched/missing intervals, coverage, cache age, and the **limitations list**.
3. Status is deliberately neutral: `all intervals matched` or `incomplete coverage` —
   the app never claims the feed is "verified".
4. Export the underlying rows if you want to check them yourself:

```bash
curl -OJ "http://127.0.0.1:8000/api/export.csv?start=2026-01-01&end=2026-01-31&grain=halfhourly"
```

Timestamps are ISO 8601 UTC; missing values are **empty** fields, never `0`.

---

## 4. Reading the metrics

All metrics are computed by the backend **over matched intervals only** (both forecast and
actual present):

| Metric | Meaning | Watch out for |
|---|---|---|
| **MAE** | mean \|F − A\| — typical miss in MW | read with coverage |
| **RMSE** | √(mean (F − A)²) — penalises big misses | always ≥ MAE; the gap = tail risk |
| **Bias** | mean (**F − A**) — **positive = over-forecast** | the direction you can plan around |
| **MAPE** | mean \|F − A\| / \|A\| × 100 | intervals with actual = 0 excluded and counted |
| **Coverage** | matched ÷ expected × 100 | `coverage_complete` only when 100 % |
| **Median / P90 \|error\|** | robust spread of the error | historical statistic, **not** a confidence bound |
| **Status counts** | matched / forecast_only / actual_only / missing_both | explains every gap |

Conventions you can rely on:

- `error_mw` = **F − A** on every row and chart.
- Missing data renders as a chart gap or "—", **never** as 0.
- When nothing matches, metrics are `null`, never `0`.

---

## 5. Filters and options reference

| Control | Where | Effect |
|---|---|---|
| Start / End date | Filter bar | Delivery-date range; constrained to the reporting period (out-of-range → 400) |
| Aggregation | Filter bar | Half-hourly (48/day) · Hourly (24/day) · Daily (means, complete days only) |
| Reset | Filter bar | Back to 1–31 Jan 2026, half-hourly |
| `?refresh=true` | any data endpoint | Forces a reload of the cached dataset |
| `?fuel_type=` | any data endpoint | FUELHH fuel filter (`WIND` default; `NUCLEAR`, `CCGT`, … also accepted). **Only `WIND` has a WINDFOR forecast** — other fuels load actuals-only and report `actual_only` for every interval |
| `?theme=dark\|light` | URL | Overrides the theme for screenshots/sharing; also toggled in the header and persisted in `localStorage` |
| Sort / page | Data table | Sort any column; page size is fixed at the bottom of the table |

Useful API-only parameters:

```bash
# different reporting period (must stay within PERIOD_START..PERIOD_END)
curl -s "http://127.0.0.1:8000/api/timeseries?start=2026-01-15&end=2026-01-16&grain=hourly"

# a different fuel: actuals only, no forecast comparison
curl -s "http://127.0.0.1:8000/api/data-quality?fuel_type=NUCLEAR"
```

---

## 6. API cheat sheet

| Method | Path | Use it to… |
|---|---|---|
| GET | `/health` | check liveness, period, cutoff, cache state (no upstream call) |
| GET | `/api/overview` | get both grains of headline stats + the selected-vintage audit list |
| GET | `/api/timeseries?start&end&grain` | pull aligned rows (chart/table/CSV source) |
| GET | `/api/accuracy?start&end&grain` | pull metrics for a range |
| GET | `/api/forecasts/latest?delivery_date` | see the eligible-at-cutoff vintage + ignored post-cutoff ones |
| GET | `/api/forecasts/vintages?date&period` | replay every publication for one half-hour |
| GET | `/api/data-quality` | audit the served dataset |
| GET | `/api/insights?start&end&grain` | get the deterministic findings for a range |
| GET | `/api/export.csv?start&end&grain` | download the rows as CSV |

Errors are always `{"detail": "…"}`: **400** validation, **422** schema, **502** upstream
Elexon failure (the real upstream message is preserved).

Interactive docs (Swagger UI) are served by FastAPI at `http://localhost:8000/docs`.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Backend unreachable — start the API server and retry." | API not running / wrong base URL | Start the backend; for the dev server check the proxy, for a deployed frontend ensure no stale/empty `VITE_API_BASE` is set in the host's env (the production fallback points at the deployed backend) |
| Slow first request (~4–6 s) | Cold dataset fetch from Elexon | Normal; cached for `CACHE_TTL_SECONDS` (3600) afterwards |
| CORS error in the browser | Backend reached cross-origin without the origin allow-listed | The deployed frontend origin is built in; if you host elsewhere, add your origin to `ALLOWED_ORIGINS` (it extends, never replaces, the built-in list), or use the Docker/nginx same-origin path |
| 400 `unknown fuel type …` | `?fuel_type=` value not in Elexon's fuel list | Use a value from the message (e.g. `WIND`, `NUCLEAR`, `CCGT`) |
| 400 `range must be within the reporting period` | Start/end outside `PERIOD_START..PERIOD_END` | Keep the range inside the configured period |
| 502 with an Elexon message | Upstream failure after 3 retries | Retry; check `http://localhost:8000/health` and network access to `data.elexon.co.uk` |
| Empty forecast column for a non-wind fuel | WINDFOR publishes wind only | Expected — the Data Quality panel states it in `sources.forecast` and `limitations` |
| Dashboard shows zeros | It never does | Missing values are `null` → gaps / "—" / empty CSV fields. If you see 0, check you are not reading a genuine zero |
| Port 8080/8081 already in use | Another local proxy | Change the published port in `docker-compose.yml` |
| Frontend can't reach the API in Docker | Backend container not healthy yet | Compose waits on the backend `HEALTHCHECK`; check `docker compose ps` |

---

## 8. Tests (before you hand this to anyone)

```bash
# backend — 88 tests
cd backend && ../.venv/bin/python -m pytest

# frontend — 40 tests (+1 gated live test)
cd frontend && npm test

# opt-in: run the live integration test against a running backend
cd frontend && LIVE=1 VITE_API_BASE=http://127.0.0.1:8000 npm test

# upstream contract verification against the real Elexon API
python3 scripts/verify_api.py
```

---

*Data © Elexon / National Grid ESO via the public BMRS API.*
