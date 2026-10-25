/** Decision Lab (Feature G): what-if decision cutoffs, envelope calibration
 *  and skill vs persistence.
 *
 *  This component only renders backend-computed figures (GET
 *  /api/forecasts/cutoff-sensitivity and GET /api/benchmarks); every number
 *  carries its sample size and the historical-what-if caveat. No LLM, no
 *  recommendations - the charts show what the accuracy *was* under different
 *  gates on the selected range. */
import { useEffect, useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, api } from "../api/client";
import type {
  BenchmarksResponse,
  CutoffCandidate,
  CutoffSensitivityResponse,
} from "../api/types";
import { formatMw } from "../lib/aggregate";
import { useTheme } from "../theme";

interface Props {
  start: string;
  end: string;
}

interface ChartRow {
  label: string;
  mae: number | null;
  rmse: number | null;
  candidate: CutoffCandidate;
}

interface TipPayload {
  payload?: ChartRow;
}

function sign(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const signText = value > 0 ? "+" : "";
  return `${signText}${value.toFixed(1)} MW`;
}

function CutoffTooltip({ active, payload, current }: { active?: boolean; payload?: TipPayload[]; current: string }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const c = row.candidate;
  return (
    <div className="rounded-md border border-ink-200 bg-surface px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-ink-900">
        Cutoff {c.cutoff_utc} UTC on D-1 {c.is_current && "· current"}
      </div>
      <div className="mt-1 font-mono text-signal-600">MAE: {formatMw(c.mae_mw)}</div>
      <div className="font-mono text-ink-700">RMSE: {formatMw(c.rmse_mw)}</div>
      <div className="font-mono text-ink-700">Bias (F − A): {sign(c.bias_mw)}</div>
      <div className="mt-1 text-ink-500">
        Δ MAE vs current {current}: {sign(c.delta_mae_mw)} (negative = lower error)
      </div>
      <div className="text-ink-500">
        {c.n_matched} matched hours, coverage {c.coverage_pct.toFixed(1)}%
      </div>
    </div>
  );
}

function CutoffCard({ data }: { data: CutoffSensitivityResponse }) {
  const { colors } = useTheme();
  if (data.candidates.length === 0) {
    return (
      <section aria-label="Decision cutoff sensitivity" className="card">
        <h2 className="text-sm font-semibold text-ink-900">Decision cutoff sensitivity</h2>
        <p className="mt-2 text-xs text-ink-500" role="status">
          {data.limitation ?? "No candidate cutoffs are available for this range."}
        </p>
      </section>
    );
  }
  const rows: ChartRow[] = data.candidates.map((candidate) => ({
    label: candidate.cutoff_utc,
    mae: candidate.mae_mw,
    rmse: candidate.rmse_mw,
    candidate,
  }));
  return (
    <section aria-label="Decision cutoff sensitivity" className="card">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Decision cutoff sensitivity</h2>
          <p className="text-xs text-ink-500">
            What hourly MAE would have been at each decision gate (same selection rule, cutoff
            moved on D-1)
          </p>
        </div>
        <p className="text-xs text-ink-500">
          Current gate: <span className="font-semibold text-amberish-600">{data.current_cutoff_utc} UTC</span>
        </p>
      </div>
      {data.best_cutoff_utc && data.best_delta_mae_mw !== null && (
        <p
          className={`mb-2 rounded-md border px-3 py-2 text-xs ${
            data.best_delta_mae_mw < 0
              ? "border-signal-500/30 bg-signal-500/10 text-signal-600"
              : "border-ink-200 bg-ink-50 text-ink-600"
          }`}
        >
          Lowest MAE on this range: <span className="font-semibold">{data.best_cutoff_utc} UTC</span>{" "}
          ({sign(data.best_delta_mae_mw)} vs the current gate) — historical what-if over{" "}
          {data.start}..{data.end}, not a recommendation.
        </p>
      )}
      <div
        role="img"
        aria-label="Chart of hourly MAE by candidate decision cutoff"
        className="h-64"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="label"
              interval={0}
              tick={{ fontSize: 10, fill: colors.axis }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: colors.axis }}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`}
              width={48}
              label={{ value: "MW", position: "insideTopLeft", fontSize: 11, fill: colors.axis }}
            />
            <Tooltip content={<CutoffTooltip current={data.current_cutoff_utc} />} />
            <Bar dataKey="mae" name="MAE" isAnimationActive={false} barSize={26}>
              {rows.map((row) => (
                <Cell
                  key={row.label}
                  fill={row.candidate.is_current ? colors.flag : colors.bar}
                  fillOpacity={row.candidate.is_current ? 1 : 0.55}
                />
              ))}
            </Bar>
            <Line
              type="monotone"
              dataKey="rmse"
              name="RMSE"
              stroke={colors.forecast}
              strokeWidth={1.6}
              dot={{ r: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[11px] text-ink-400">{data.note}</p>
    </section>
  );
}

function StatTile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2">
      <div className="kpi-label">{label}</div>
      <div className="text-lg font-semibold text-ink-900">{value}</div>
      <p className="text-[11px] text-ink-500">{hint}</p>
    </div>
  );
}

function BenchmarksCard({ data }: { data: BenchmarksResponse }) {
  const { calibration, skill } = data;
  const evaluated = calibration.hours_evaluated;
  const share = (count: number) =>
    evaluated > 0 ? `${((100 * count) / evaluated).toFixed(1)}%` : "—";
  const skillTone =
    skill.skill_pct === null ? "text-ink-500" : skill.skill_pct >= 0 ? "text-signal-600" : "text-amberish-600";
  return (
    <section aria-label="Calibration and skill" className="grid gap-3 lg:grid-cols-2">
      <div className="card">
        <h2 className="text-sm font-semibold text-ink-900">Envelope calibration</h2>
        <p className="text-xs text-ink-500">
          Did the actual land inside the min–max spread of the pre-cutoff vintages?
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <StatTile
            label="Inside"
            value={share(calibration.hours_inside)}
            hint={`${calibration.hours_inside} h`}
          />
          <StatTile
            label="Below"
            value={share(calibration.hours_below)}
            hint="actual under envelope"
          />
          <StatTile
            label="Above"
            value={share(calibration.hours_above)}
            hint="actual over envelope"
          />
        </div>
        <dl className="mt-3 space-y-1 text-xs text-ink-600">
          <div className="flex justify-between gap-2">
            <dt>Evaluated hours</dt>
            <dd className="font-mono text-ink-800">
              {calibration.hours_evaluated} of {calibration.hours_total}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>Avg envelope width</dt>
            <dd className="font-mono text-ink-800">{formatMw(calibration.avg_envelope_width_mw)}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>Avg vintages per hour</dt>
            <dd className="font-mono text-ink-800">
              {calibration.avg_vintages_per_hour ?? "—"}
            </dd>
          </div>
        </dl>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-400">{calibration.limitation}</p>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-ink-900">Skill vs persistence</h2>
        <p className="text-xs text-ink-500">
          Did the decision-time forecast beat yesterday&apos;s outturn at the same half-hour?
        </p>
        <div className="mt-3">
          <div className="kpi-label">Skill score</div>
          <div className={`kpi-value ${skillTone}`}>
            {skill.skill_pct === null ? "—" : `${skill.skill_pct > 0 ? "+" : ""}${skill.skill_pct.toFixed(1)}%`}
          </div>
          <p className="mt-1 text-xs text-ink-500">
            100 × (1 − forecast MAE ÷ persistence MAE); positive = forecast wins
          </p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <StatTile
            label="Forecast MAE"
            value={formatMw(skill.windfor_mae_mw)}
            hint="WINDFOR, half-hourly"
          />
          <StatTile
            label="Persistence MAE"
            value={formatMw(skill.persistence_mae_mw)}
            hint="actual 24h earlier"
          />
        </div>
        <dl className="mt-3 space-y-1 text-xs text-ink-600">
          <div className="flex justify-between gap-2">
            <dt>Common sample</dt>
            <dd className="font-mono text-ink-800">
              {skill.n_evaluated} of {skill.n_matched} matched intervals
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>Excluded (no prior-day actual)</dt>
            <dd className="font-mono text-ink-800">{skill.n_persistence_unavailable}</dd>
          </div>
        </dl>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-400">{skill.note}</p>
      </div>
    </section>
  );
}

export default function DecisionLab({ start, end }: Props) {
  const [cutoff, setCutoff] = useState<CutoffSensitivityResponse | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setCutoff(null);
    setBenchmarks(null);
    Promise.all([
      api.cutoffSensitivity({ start, end }, controller.signal),
      api.benchmarks({ start, end }, controller.signal),
    ])
      .then(([nextCutoff, nextBenchmarks]) => {
        setCutoff(nextCutoff);
        setBenchmarks(nextBenchmarks);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Unexpected error");
      });
    return () => controller.abort();
  }, [start, end, attempt]);

  if (error) {
    return (
      <section aria-label="Decision Lab" className="card">
        <h2 className="text-sm font-semibold text-ink-900">Decision Lab</h2>
        <p className="mt-2 text-xs text-ink-500" role="status">
          Decision Lab unavailable ({error}).{" "}
          <button type="button" className="underline" onClick={() => setAttempt((a) => a + 1)}>
            Retry
          </button>
        </p>
      </section>
    );
  }
  if (!cutoff || !benchmarks) {
    return (
      <section aria-label="Decision Lab" className="card">
        <h2 className="text-sm font-semibold text-ink-900">Decision Lab</h2>
        <p className="mt-2 text-xs text-ink-500" role="status">
          Computing cutoff sensitivity, calibration and skill…
        </p>
      </section>
    );
  }

  return (
    <div aria-label="Decision Lab" className="space-y-3">
      <CutoffCard data={cutoff} />
      <BenchmarksCard data={benchmarks} />
      <p className="text-xs text-ink-500">{benchmarks.note}</p>
    </div>
  );
}
