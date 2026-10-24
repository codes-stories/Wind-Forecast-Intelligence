import type { HealthResponse } from "../api/types";
import { useTheme } from "../theme";

interface Props {
  health: HealthResponse | null;
}

const MOON_PATH = "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z";
const SUN_RAYS = [
  "M12 2v2",
  "M12 20v2",
  "M4.93 4.93l1.41 1.41",
  "M17.66 17.66l1.41 1.41",
  "M2 12h2",
  "M20 12h2",
  "M6.34 17.66l1.41-1.41",
  "M19.07 4.93l1.41-1.41",
];

function ThemeIcon({ dark }: { dark: boolean }) {
  if (dark) {
    // moon shown while dark -> switching to light
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={MOON_PATH} />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      {SUN_RAYS.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

export default function Header({ health }: Props) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const periodLabel =
    health ? `Reporting period: ${health.period_start} — ${health.period_end}` : "Reporting period: January 2026";
  const cutoff = health?.decision_cutoff_utc ?? "09:20";

  return (
    <header className="border-b border-ink-200 bg-surface">
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
        <button
          type="button"
          onClick={toggle}
          className="btn inline-flex items-center gap-1.5 self-center"
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          title={dark ? "Switch to light mode" : "Switch to dark mode"}
        >
          <ThemeIcon dark={dark} />
          <span className="hidden sm:inline">{dark ? "Light" : "Dark"}</span>
        </button>
      </div>
    </header>
  );
}
