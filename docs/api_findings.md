# Phase 1 — Data-source and API findings

**Status: complete.** Every statement below was verified live against the Elexon
Insights (BMRS) API or taken verbatim from a cited official source. Verified by
`scripts/verify_api.py` (27/27 checks pass) and `scripts/fetch_samples.py`
(all sample integrity checks pass). Nothing is fabricated or substituted.

Run: `python3 scripts/verify_api.py` (≈40 s, stdlib only, exit 0 = pass).

---

## 1. Repository inspection

The repository was empty at the start of Phase 1 (no prior work to preserve).
Files created in Phase 1 only:

```
docs/api_findings.md      # this document
scripts/verify_api.py     # live verification probe (27 assertions)
scripts/fetch_samples.py  # fetches the verified sample records
data/samples/*.json       # verified actual + forecast samples + manifest
```

### Proposed structure (not yet generated — for approval before Phase 2)

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, router mounting
│   │   ├── config.py          # cutoff time, study period (env-overridable)
│   │   ├── elexon.py          # API client (FUELHH, WINDFOR), retry, caching
│   │   ├── selection.py       # point-in-time forecast selection rule
│   │   ├── metrics.py         # MAE/RMSE/bias/over-under, daily + half-hourly
│   │   └── routers/           # /api/analysis, /api/series, /api/health
│   ├── tests/                 # pytest: selection, metrics, client, api
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                  # Vite + React + TypeScript
│   ├── src/{components,pages,api,types}/
│   ├── src/**/*.test.tsx      # Vitest + React Testing Library
│   └── Dockerfile
├── docker-compose.yml
├── docs/
└── scripts/
```

---

## 2. API access method

The documentation URLs given in the assignment are a JavaScript app and cannot
be fetched directly. The machine-readable specification was obtained from:

- OpenAPI spec: `https://data.elexon.co.uk/swagger/v1/swagger.json` (title `Insights.Api`)
- **Base URL: `https://data.elexon.co.uk/bmrs/api/v1`** (declared in the spec)

No API key required. `Accept: application/json` (or `?format=json`).
Responses: `application/json; charset=utf-8`, `Cache-Control: no-store`.
**No pagination**: no pagination parameters in the spec and no pagination
headers; a full-window query returned every row in one response (verified with
an 18,688-row / 2.1 MB response).

Endpoints used:

| Purpose | Endpoint |
|---|---|
| Actuals | `GET /datasets/FUELHH/stream` |
| Forecasts (bulk, all vintages) | `GET /datasets/WINDFOR/stream` |
| Forecast cross-check (one vintage) | `GET /forecast/generation/wind/history?publishTime=` |
| Forecast evolution (all vintages of one interval) | `GET /forecast/generation/wind/evolution?startTime=` |

Not used: `GET /forecast/generation/wind/latest` — it returns the **post-hoc
latest** vintage per interval; using it would leak future information into a
retrospective evaluation.

## 3. Request parameters and date-filter semantics

### FUELHH (actuals)

| Parameter | Type | Semantics |
|---|---|---|
| `settlementDateFrom` / `settlementDateTo` | `yyyy-MM-dd` | inclusive delivery-date range |
| `publishDateTimeFrom` / `publishDateTimeTo` | ISO datetime UTC | inclusive publication-time range |
| `fuelType` | array, e.g. `WIND` | filter on fuel type |
| `settlementPeriod` | array of ints 1–48 | filter on settlement period |

**Rule (verified HTTP 400):** settlement-date filters and publish-date filters
cannot be combined —
`"The Settlement Date fields cannot be set when a Publish Date field is set."`
Also verified: `publishDateTimeFrom > publishDateTimeTo` → HTTP 400 with a
validation message. Date format for settlement dates must be `yyyy-MM-dd`.

### WINDFOR (forecasts)

| Parameter | Type | Semantics |
|---|---|---|
| `publishDateTimeFrom` / `publishDateTimeTo` | ISO datetime UTC | inclusive **publication-time** range |

No settlement-date, fuel-type or settlement-period filters exist on the stream
endpoint. Forecasts are addressed by **publication time**, then keyed to
delivery by `startTime`.

## 4. Example response schemas (from the OpenAPI spec, matched by live data)

**FUELHH stream — array of:**

```json
{"dataset": "FUELHH",
 "publishTime": "2026-01-02T00:00:00Z",
 "startTime":   "2026-01-01T23:30:00Z",
 "settlementDate": "2026-01-01",
 "settlementPeriod": 48,
 "fuelType": "WIND",
 "generation": 15538}
```

**WINDFOR stream — array of:**

```json
{"dataset": "WINDFOR",
 "publishTime": "2026-01-01T04:30:00Z",
 "startTime":   "2025-12-31T21:00:00Z",
 "generation": 19498}
```

**WINDFOR history/evolution — `{metadata, data:[...]}` with settlement keys:**

```json
{"metadata": {"datasets": ["WINDFOR"]},
 "data": [{"publishTime": "2026-01-14T07:30:00Z",
           "startTime":   "2026-01-14T00:00:00Z",
           "settlementDate": "2026-01-14",
           "settlementPeriod": 1,
           "generation": 10739}]}
```

All fields observed non-null in the January 2026 windows queried.

## 5. Meaning of timestamps and units

- **`startTime`** = start of the **delivery interval** (UTC, `Z` suffix).
  Half-hourly for FUELHH (:00 and :30); hourly for WINDFOR (always minute `00`).
- **`publishTime`** = when the record was **published** (UTC). For FUELHH it is
  the end of the delivery interval (`startTime` + 30 min) — outturn, published
  after delivery. For WINDFOR it is the forecast run/publication time; the same
  `publishTime` stamps all 73 rows of one vintage.
- **Units:** no unit is declared in either the schema, the CSV header
  (`Generation`), or `/datasets/metadata/latest` (which returns only
  `dataset` + `lastUpdated`).
  - FUELHH spec text: *"average MW values over 30 minutes"* → **MW is
    documented for actuals**.
  - WINDFOR: **not documented → MW is an explicit assumption.** Supporting
    evidence: same-magnitude cross-check on delivery day 2026-01-15 —
    actuals 7,183–14,602 MW vs forecast 8,864–15,834 MW (GB wind installed
    capacity ≈ 30 GW). Recorded in `data/samples/manifest.json`.
- All timestamps are UTC; January 2026 is GMT, so UTC == UK local time for the
  whole study period.

## 6. Historical forecast vintages — how they are retrieved

**Retrievable in full — no limitation for the study period.**

```
GET /datasets/WINDFOR/stream
    ?publishDateTimeFrom=2025-12-31T00:00:00Z
    &publishDateTimeTo=2026-02-01T00:00:00Z
→ 18,688 rows = 256 vintages × 73 rows
```

Verified properties:

- **8 vintages per publication day, every day** (32/32 days): at
  **02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30, 22:30 UTC**.
- Each vintage = **73 hourly points**, coverage
  **(publish date − 1) 21:00 UTC → (publish date + 2) 21:00 UTC**; all 8
  vintages of a day share that window.
- Cross-check: `/forecast/generation/wind/history?publishTime=2026-01-14T07:30:00Z`
  and the stream return **identical values** (73/73 rows, 0 mismatches).
- Zero duplicate `(publishTime, startTime)` keys, zero nulls, zero negatives
  across all 18,688 rows (range 2,250–21,353 MW).
- The spec text claims publication at "03:30, 05:30, 08:30 … 23:30"; the
  **observed** timestamps in January 2026 are one hour earlier
  (02:30 … 22:30 UTC). Observed data is treated as authoritative.

## 7. Actuals — sample and completeness

- January 2026 `fuelType=WIND`: **1,488 rows = 31 days × 48 settlement
  periods**, every day complete, `settlementPeriod` ∈ 1..48, zero duplicates,
  zero nulls, zero negatives (range 1,695–17,805 MW).
- Publish-windowed query (2026-01-15 → 2026-01-20): 241 rows, 241 unique
  settlement periods → **no restatement duplicates**; one row per period.
- Sample: `data/samples/fuelhh_2026-01-15_wind.json` (48 verified rows).

## 8. Half-hourly delivery coverage (task 9)

| Series | Granularity | Coverage per delivery day |
|---|---|---|
| FUELHH actual | half-hourly | **48/48** settlement periods (verified 31/31 days) |
| WINDFOR forecast | hourly | **24/48** settlement periods — only odd periods 1, 3, 5 … 47 |

- Verified on the full month: all 18,688 forecast `startTime`s are on minute
  `00`; via the history endpoint the vintage's `settlementPeriod` set is exactly
  `{1,3,5,…,47}` (24 values, all odd).
- **There are no half-hourly forecast values in WINDFOR.** Half-hourly
  comparison therefore requires a documented mapping: the hourly forecast value
  is applied to both half-hours of its clock hour. Hourly aggregation (mean of
  the two half-hourly actuals) is the lossless alternative and will be the
  primary comparison grain; the mapping is a stated assumption, never silent.

## 9. Day-ahead decision cutoff

**Market facts (authoritative, primary source fetched):**

- EPEX SPOT Trading Products page
  (<https://www.epexspot.com/en/tradingproducts>), quoted verbatim:
  - Day-ahead auction: *"Closure of orderbook: daily at 12:00 (CET)
    (**9:20 GMT for Great Britain** …) in D-1"*, *"Publication of results: from
    12:55 (CET) onwards (**9:30 GMT for Great Britain** …)"*.
  - GB half-hour day-ahead auction: *"Closure of orderbook: daily at 15:30
    (GMT) in D-1"*, results from 15:45 GMT.
  - GB intraday auctions: 17:30 GMT (D-1) and 08:00 GMT (delivery day).
- DESNZ consultation government response (gov.uk, 2023-08-23) independently
  describes the two GB hourly day-ahead auctions "at 09:20 and 09:50"
  (EPEX SPOT and Nord Pool N2EX).

**Chosen default — labelled as an assumption requiring confirmation:**

> `decision_cutoff = 09:20 UTC (GMT) on D-1`, the EPEX SPOT GB day-ahead
> order-book closure.

The *market* gate closure is documented fact; the claim that *our analyst's
procurement decision* coincides with it is an **assumption**. It is therefore
exposed as configuration (`decision_cutoff` time-of-day, applied to D-1,
default `09:20Z`) and documented in the README. If the client confirms a
different deadline (e.g. 15:30 GMT for the half-hour auction, or 09:50 GMT for
N2EX), the same rule yields the corresponding later vintage with no code change.

## 10. Forecast-selection rule (point-in-time, retrospective)

For each delivery day D (January 2026):

1. Consider only vintages with `publishTime <= cutoff(D-1)` where `cutoff(D-1)`
   is the configured decision time on the day before delivery
   (default `D-1 09:20:00Z`).
2. Require the vintage to cover **all 24 hourly points** of day D
   (its coverage window must contain 00:00 … 23:00 UTC of D).
3. Select the vintage with the **maximum `publishTime`** — the newest
   information available at the decision moment.
4. Join to actuals on delivery time (`startTime`), applying the §8
   half-hourly mapping where the half-hourly view is displayed.
5. **Never** use `/forecast/generation/wind/latest` or any post-cutoff vintage
   for historical accuracy figures; preserve the selected vintage's original
   `publishTime` for audit.

**Verified outcome:** for **31/31 days** the rule selects the vintage published
at **07:30 UTC on D-1**; the 09:30 UTC vintage is always published after the
09:20 cutoff and is therefore ineligible. 0 missing days.

Examples saved: eligible `data/samples/windfor_vintage_2026-01-14T0730Z.json`
(73 rows, covers all of Jan 15) vs post-cutoff
`data/samples/windfor_vintage_2026-01-14T0930Z.json` (ineligible example).

## 11. Data-quality findings summary

| Check | FUELHH (Jan 2026) | WINDFOR (vintages covering Jan 2026) |
|---|---|---|
| Rows | 1,488 (31×48 complete) | 18,688 (256 vintages × 73) |
| Duplicate keys | 0 | 0 |
| Null `generation` | 0 | 0 |
| Negative `generation` | 0 | 0 |
| Missing days/periods | 0 | 0 missing vintages (8/day × 32) |
| Restatements seen | none | n/a |
| Timestamp convention | UTC `Z` | UTC `Z` |

API limitations observed:

- WINDFOR stream has **publish-time filters only** (no settlement-date filter).
- FUELHH **cannot combine** settlement and publish filters (400).
- No pagination (single large responses; 2.1 MB observed and accepted).
- WINDFOR is hourly — no half-hourly forecast grain exists.
- Units undocumented for WINDFOR (assumption §5).
- Historical depth spot-checked only for 2025-12-31 → 2026-02-01.

## 12. Risks / missing data

1. **Units (WINDFOR)** — assumption, magnitude-supported, not declared. Risk: low.
2. **Decision cutoff** — market gate closure is sourced; the analyst's exact
   decision moment is an assumption → configurable + documented. Risk: low.
3. **Grain mismatch** — hourly forecast vs half-hourly actual → documented
   mapping; hourly is the primary grain. Risk: medium for half-hourly claims.
4. **Restatement** — no restatements observed for FUELHH in January 2026; if
   Elexon restates later, results could shift slightly. Risk: low.
5. **Retention** — vintage depth verified only for the study window; long-term
   retention beyond it is not guaranteed. Risk: low for this project.
6. **Integer rounding** — `generation` is an integer (±0.5 MW quantisation).
   Risk: negligible.

No missing actuals, no missing vintages, no nulls, no duplicate keys were found
for the study period. Nothing was substituted or fabricated.

## 13. Sufficiency recommendation

**The data is sufficient to proceed to Phase 2.** Historical forecast vintages
with publication timestamps are fully retrievable for January 2026; actuals are
complete at half-hourly grain with no gaps or duplicates; a defensible
point-in-time selection rule is verified for all 31 days; the two open items
(WINDFOR units, exact decision time) are documented assumptions that are
configurable rather than blocking.

## 14. Sample records (deliverable)

| File | Contents |
|---|---|
| `data/samples/fuelhh_2026-01-15_wind.json` | 48 half-hourly actual rows (WIND) |
| `data/samples/windfor_vintage_2026-01-14T0730Z.json` | 73 rows — eligible D-1 07:30 vintage |
| `data/samples/windfor_vintage_2026-01-14T0930Z.json` | 73 rows — post-cutoff vintage (ineligible) |
| `data/samples/manifest.json` | request URLs, fetch time, integrity checks |

Regenerate with `python3 scripts/fetch_samples.py`.
