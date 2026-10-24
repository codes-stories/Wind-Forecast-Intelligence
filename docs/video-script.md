# Final Demonstration Video — Recording Script

**Target:** one YouTube video, **unlisted**, total **≤ 10:00**
**Part 1 (Customer presentation): ≤ 5:00** · **Part 2 (Technical review): ≤ 5:00**

> Status: **SCRIPT ONLY — not yet recorded.** Follow the run sheet, record each part,
> check durations in YouTube Studio (must be ≤ 10:00 combined), upload as **Unlisted**.

---

## Recording run sheet (before you start)

1. Start the stack: `docker compose up --build` → dashboard at `http://localhost:8081`
   (alternatively backend `:8000` + `npm run dev` at `:5173`).
2. Open an **incognito window** at the dashboard URL; wait for KPIs to load (~5 s first load).
3. Keep these tabs ready: dashboard · `http://localhost:8000/api/overview` · `backend/app/services/forecast_service.py` · `docker-compose.yml`.
4. Record Part 1 and Part 2 separately if easier; splice in order. Keep each part ≤ 5:00.

---

# PART 1 — Customer presentation (≤ 5:00)

*Presenter: product developer, pilot-project demo. Tone: business user, not engineer.*

### 0:00–0:30 — The procurement problem
- Screen: incognito window on the dashboard, full page.
- Say: *“Day-ahead, a buyer commits to wind volumes for tomorrow before the market gate
  closes. If the forecast is systematically wrong, they over- or under-buy. The first question
  isn't ‘what's the P&L’ — it’s ‘how reliable was the forecast we were acting on?’”*
- One line only: this pilot evaluates forecast reliability — it does **not** calculate a
  complete electricity trading position.

### 0:30–1:30 — The dashboard and reporting period
- Point at header: reporting period **1–31 January 2026**, data source **Elexon BMRS**
  (FUELHH actual vs WINDFOR forecast), badge **decision cutoff 09:20 UTC on D−1**.
- Show the filter bar: date range + aggregation (half-hourly / daily), Reset button.
- Say: *“One month, every half-hour, real published grid data — no samples, no estimates.”*

### 1:30–2:30 — Forecast versus actual
- Scroll to **Forecast vs actual generation**. Hover two points: one where lines are close,
  one where the blue line is well above amber.
- Say: *“Blue is the decision-time forecast; amber is what actually generated. Gaps would mean
  missing data — we never fill them with zero.”*
- Optionally switch aggregation to **Daily** and back to show the chart re-render.

### 2:30–3:30 — MAE, RMSE, bias, coverage in business terms
- Frame the six KPI cards.
- **MAE ~2,145 MW:** *“the typical miss is about 2.1 GW on a fleet averaging ~11.6 GW.”*
- **RMSE ~2,616 MW:** *“bigger misses hurt more — RMSE punishes the bad days harder than MAE.”*
- **Bias +1,852 MW:** *“positive means forecast minus actual — we over-forecast on average by
  about 1.9 GW. That's a systematic, one-directional error, the kind you can plan around.”*
- **Coverage 100% (1,488 of 1,488):** *“every interval in the month has both forecast and
  actual — so these numbers aren't a sample, they're the whole month.”*
- Do not claim savings, revenue, or trading impact.

### 3:30–4:30 — Inspecting one delivery interval
- Scroll to **Historical delivery data**. Sort by “Absolute error” descending; open the top row.
- Read the row: delivery timestamp, forecast, actual, signed error, and
  **Forecast published (UTC)** — e.g. delivery `01 Jan 00:00 UTC` uses the vintage published
  `31 Dec 07:30 UTC`.
- Say: *“Every number is traceable to the exact publication an analyst would have seen before
  the gate closed. Post-cutoff revisions are never used — that's the whole point.”*
- Point at the availability badge (`matched` / `forecast only`) and the “— means missing, not zero” note.

### 4:30–5:00 — Value, limitations, next steps
- Value: *“It turns ‘we think the forecast is okay’ into auditable numbers per interval.”*
- Limitations (be explicit): January 2026 only; MW for forecasts is an assumption (Elexon
  doesn't document WINDFOR units); it measures reliability, not a trading position.
- Next steps: deployment to Vercel + Render, more months, scheduled refresh.
- End Part 1 on the KPI row. **Target duration ≤ 5:00.**

---

# PART 2 — Technical review (≤ 5:00)

*Presenter: same person, engineer voice. Show real code/behavior; explain decisions, don't read files.*

### 0:00–0:45 — Architecture and technology choices
- Screen: ASCII diagram from `README.md` §5 (or draw live).
- Say: *“FastAPI + Pydantic backend; React/TypeScript/Vite frontend; Recharts for visuals.
  No database — one in-memory dataset for the study period with a 1-hour TTL, because the
  whole month is ~1.5k actual rows plus ~18.7k forecast rows.”*
- Decision: *“Why no DB? The dataset is fixed and small; a cache invalidation problem would be
  more complexity than value for a retrospective pilot.”*

### 0:45–1:45 — Elexon API integration and historical data handling
- Show `scripts/verify_api.py` output or `docs/api_findings.md` highlights.
- Points: FUELHH is half-hourly (48/day) with **mutually exclusive** date filters (mixing
  them → HTTP 400 — we hit this and encoded it). WINDFOR has **8 vintages/day** and only
  publish-time filters, so we fetch a publish window and filter delivery days ourselves.
- Numbers: **18,688** WINDFOR rows fetched, **256** vintages, **0** duplicates dropped;
  FUELHH **1,488/1,488**, no nulls.
- Decision: *“We keep Elexon's raw publish timestamps untouched — we only select, never rewrite.”*

### 1:45–2:45 — Forecast selection, timestamp alignment, error metrics
- Show `forecast_service.py`: `decision_cutoff_for()` = **09:20 UTC on D−1**, then
  “latest eligible publishTime wins” per delivery hour.
- Result: for Jan 2026 that's always the **D−1 07:30** vintage — audited **0 violations**
  across 1,488 intervals; `/api/forecasts/latest` also lists ignored post-cutoff vintages.
- Alignment: hourly forecast mapped to both half-hours; hourly actual = mean of the two
  half-hours, **both required** or the interval is unmatched — no interpolation, no zero-fill.
- Metrics: MAE/RMSE/bias over **matched intervals only**; bias = mean(F − A) so **positive =
  over-forecast**; MAPE excludes actual = 0 and counts exclusions; coverage always shown.
- Independent audit recomputed every metric from `/api/timeseries` and matched the API to 3 decimals.

### 2:45–3:45 — Code structure, testing, error handling
- Quick map: `routes.py` (contracts) → `forecast_service` (select/align/cache) →
  `metrics_service` (statistics); schemas are the single source of truth mirrored in `types.ts`.
- Tests on screen: `55 passed` (pytest) · `16 passed` (vitest) · optional
  `LIVE=1 … npm test` → **17th integration test against the real backend**.
- Error handling: validation → 400/422 with machine-readable `detail`; upstream failure → 502
  with the real Elexon error; frontend shows a retryable error panel; missing data renders as
  gaps/“—”, never as zero. CORS restricted to `ALLOWED_ORIGINS` (this audit found and fixed a
  wildcard-`*` config).

### 3:45–4:30 — Docker and deployment
- Show `docker compose up --build`; hit `http://localhost:8081` and `:8000/health`.
- Explain: backend image has a `HEALTHCHECK`; compose gates the frontend on `service_healthy`;
  frontend image is multi-stage (node build → nginx) and **proxies `/api` + `/health`**
  (`BACKEND_URL`) so local traffic is same-origin and CORS-free.
- Deployment status (be honest): frontend target **Vercel**, backend target **Render**
  (`render.yaml` blueprint, free tier — Heroku verified as card-required/paid). **Not yet
  deployed: platform credentials weren't available**, so there is no live URL to show;
  steps are in README §17.
- Environment: `VITE_API_BASE` at build time, `ALLOWED_ORIGINS` on the backend.

### 4:30–5:00 — Limitations, trade-offs, future improvements
- Trade-offs: in-memory cache dies with the process; free hosts sleep when idle; split-host
  deployment means CORS and a build-time API URL (documented in README §5).
- Limitations: WINDFOR units assumed MW; x-axis ticks show time-of-day only (data/tooltips are
  correct); single month; no persistence.
- Future: finish deployment, multi-month range, SQLite/Parquet persistence, scheduled refresh,
  CI (pytest + vitest + docker build).
- Close on `git log --oneline` or the test counts. **Target ≤ 5:00.**

---

## Duration discipline

| | Target | Hard cap |
|---|---|---|
| Part 1 | ~4:30 | **5:00** |
| Part 2 | ~4:30 | **5:00** |
| Combined | ~9:00 | **10:00** |

If over: cut from Part 2 §0:45–1:45 (API details) first — the README carries the depth.
