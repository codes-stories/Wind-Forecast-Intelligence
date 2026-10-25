import { useState } from "react";
import { exportCsvUrl } from "../api/client";

export type Aggregation = "halfhourly" | "daily";

interface Props {
  start: string;
  end: string;
  aggregation: Aggregation;
  minDate: string;
  maxDate: string;
  onChange: (next: { start?: string; end?: string; aggregation?: Aggregation }) => void;
  onReset: () => void;
}

export default function FilterBar({
  start,
  end,
  aggregation,
  minDate,
  maxDate,
  onChange,
  onReset,
}: Props) {
  const startInvalid = start > end;
  const exportGrain = aggregation === "daily" ? "hourly" : "halfhourly";
  const [copied, setCopied] = useState(false);

  const copyViewLink = async () => {
    try {
      // the address bar always reflects the current filters/tab (App effect)
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false); // clipboard unavailable (insecure context, denied)
    }
  };

  return (
    <section aria-label="Filters" className="card flex flex-wrap items-end gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="filter-start" className="kpi-label">
          From (delivery date)
        </label>
        <input
          id="filter-start"
          type="date"
          className="input"
          value={start}
          min={minDate}
          max={maxDate}
          onChange={(e) => onChange({ start: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="filter-end" className="kpi-label">
          To (delivery date)
        </label>
        <input
          id="filter-end"
          type="date"
          className="input"
          value={end}
          min={minDate}
          max={maxDate}
          onChange={(e) => onChange({ end: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="filter-grain" className="kpi-label">
          Aggregation
        </label>
        <select
          id="filter-grain"
          className="input"
          value={aggregation}
          onChange={(e) => onChange({ aggregation: e.target.value as Aggregation })}
        >
          <option value="halfhourly">Half-hourly (48/day)</option>
          <option value="daily">Daily (mean)</option>
        </select>
      </div>
      <button type="button" className="btn" onClick={onReset}>
        Reset to January 2026
      </button>
      <a
        className="btn-primary"
        href={startInvalid ? undefined : exportCsvUrl({ start, end, grain: exportGrain })}
        download={startInvalid ? undefined : `wind_forecast_${start}_${end}_${exportGrain}.csv`}
        aria-disabled={startInvalid || undefined}
        title={
          startInvalid
            ? "Fix the date range before exporting"
            : `Download the filtered rows as CSV (${exportGrain} grain); missing values are empty, never 0`
        }
        onClick={(e) => {
          if (startInvalid) e.preventDefault();
        }}
      >
        Export CSV
      </a>
      <button
        type="button"
        className="btn"
        onClick={copyViewLink}
        aria-label="Copy view link"
        title="Copy a URL that reopens this exact view: dates, aggregation and active tab"
      >
        {copied ? "Copied" : "Copy view link"}
      </button>
      <p className="ml-auto max-w-md text-xs text-ink-500">
        {startInvalid ? (
          <span role="alert" className="font-medium text-red-600">
            Start date must be on or before end date.
          </span>
        ) : (
          <>All values from the backend for the selected range. Times shown in UTC.</>
        )}
      </p>
    </section>
  );
}
