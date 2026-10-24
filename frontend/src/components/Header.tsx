import type { HealthResponse } from "../api/types";

interface Props {
  health: HealthResponse | null;
}

export default function Header({ health }: Props) {
  const periodLabel =
    health ? `Reporting period: ${health.period_start} — ${health.period_end}` : "Reporting period: January 2026";
  const cutoff = health?.decision_cutoff_utc ?? "09:20";

  return (
    <header className="border-b border-ink-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-baseline gap-x-6 gap-y-2 px-4 py-4 sm:px-6">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight text-ink-950 sm:text-xl">
            Wind Forecast Intelligence
          </h1>
          <span className="badge bg-signal-500/10 text-signal-600">Day-ahead analysis</span>
        </div>
        <p className="text-sm text-ink-600">{periodLabel}</p>
        <p className="text-sm text-ink-600">
          Data source:{" "}
          <span className="font-medium text-ink-800">Elexon BMRS</span>{" "}
          <span className="text-ink-400">(FUELHH actual · WINDFOR forecast)</span>
        </p>
        <p
          className="ml-auto rounded-md border border-amberish-400/40 bg-amberish-400/10 px-2 py-1 text-xs font-medium text-amberish-600"
          title="Historical decision cutoff used to select the forecast vintage: the latest forecast published at or before this time on the day before delivery (D-1)."
        >
          Decision cutoff: {cutoff} UTC on D-1
        </p>
      </div>
    </header>
  );
}
