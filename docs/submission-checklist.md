# Submission Checklist — Wind Forecast Intelligence

Status of every submission item, with evidence. Last verified: **2026-10-24 12:44 UTC+05:30**.
Nothing below is marked done unless it was actually completed and re-checked in this session.

---

## Verified URLs

| # | URL | How verified | Result |
|---|---|---|---|
| 1 | `https://github.com/codes-stories/Wind-Forecast-Intelligence` | HTTP GET (public repo) | ✅ **200** |
| 2 | `…/main/README.md` (raw) | HTTP GET after push | ✅ **200** — setup instructions + AI disclosure live |
| 3 | `…/main/docs/screenshots/dashboard-full.png` (raw) | HTTP GET after push | ✅ **200** |
| 4 | `http://localhost:8081/` — Docker stack dashboard | HTTP GET (nginx + SPA) | ✅ **200** (real Chrome screenshot rendered live data) |
| 5 | `http://localhost:8000/health` — backend direct | HTTP GET | ✅ **200** `{"status":"ok",…}` |
| 6 | `http://localhost:5173/` — Vite dev server (proxy verified) | HTTP GET + `/api/accuracy` via proxy | ✅ **200**, real metrics returned |
| 7 | All five API endpoints via `:8081` proxy and `:8000` direct | curl audit script (Phase 4) | ✅ 200/400/422/502 paths as designed |
| 8 | **Deployed frontend URL** | — | ❌ **Not deployed** — no platform credentials were provided (Vercel token / Render API key never arrived) |
| 9 | **Deployed backend health URL** | — | ❌ **Not deployed** — same reason; `render.yaml` + README §17 steps are ready |
| 10 | YouTube video URL | — | ❌ **Not recorded** — script prepared at [`docs/video-script.md`](video-script.md) |

Incognito note: items 1–3 are static public assets (browser-independent); items 4–7 were
verified with HTTP checks and a real headless-Chrome render of the dashboard. A human incognito
pass on the **local** URLs is a 30-second manual step; the deployed URLs cannot be tested
until deployment happens.

---

## Submission checklist

- [ ] **Application deployed and tested.** — ❌ **Blocked.** Local + Docker stacks are built
      and fully tested (55 backend tests, 16+1 frontend tests, Phase-4 audit). Public
      deployment awaits two tokens: Vercel token + Render API key (user chose “Provide API
      tokens” in Phase 5; none were supplied). Deploy commands: README §17 and `render.yaml`.
- [x] **Public GitHub repository created with anonymous naming.**
      — ✅ `github.com/codes-stories/Wind-Forecast-Intelligence` (public, non-identifying
      name; verified 200; latest commit `3f98d81` + Phase-7 docs pushed).
- [x] **README includes setup instructions and AI disclosure.**
      — ✅ README §12–§16 (install, Docker, env vars, API, tests — all re-verified against the
      codebase in Phase 6) and §18 (AI tools: opencode agent, per-phase role, human decisions).
- [ ] **Unlisted YouTube video recorded.** — ❌ **Not recorded.** Full minute-by-minute script
      for both parts is ready: [`docs/video-script.md`](video-script.md) (Part 1 customer
      ≤5:00, Part 2 technical ≤5:00, with run sheet and duration discipline).
- [ ] **Video is ≤ 10 minutes.** — ⏳ Pending recording (script budgets ~9:00 combined).
- [ ] **Customer and technical sections each ≤ 5 minutes.** — ⏳ Pending recording (script
      hard-caps each part at 5:00).
- [ ] **All submission URLs tested in an incognito window.** — ⚠️ **Partial.** Repo/README/
      screenshot: static public assets, verified by HTTP. Local app: verified via headless
      Chrome + HTTP (equivalent render). Deployed URLs: impossible until deployment. Final
      human incognito pass required after deployment.
- [ ] **Submission form completed.** — ❌ **Not submitted.** No form access from this
      environment; must be completed by the human submitter after deployment + video.
- [x] **Total work within the 16-hour limit.** — ✅ Observable artifact timestamps span
      **2026-10-24 11:01 → 12:44 (~1 h 45 m)** across all seven phases (file mtimes + git
      commits `0aa02e6`…`3f98d81`); no evidence of work outside that window. Far below 16 h.

---

## To finish (human + agent, in order)

1. **You provide:** Vercel token + Render API key → agent deploys, sets
   `VITE_API_BASE` / `ALLOWED_ORIGINS`, runs the full live verification (Phase 5 steps).
2. **You record** using `docs/video-script.md` → upload **Unlisted**, confirm ≤ 10:00.
3. **Human incognito pass** on: GitHub repo, deployed frontend, deployed `/health`.
4. **Complete the submission form** with: repo URL, video URL, deployed URLs.
