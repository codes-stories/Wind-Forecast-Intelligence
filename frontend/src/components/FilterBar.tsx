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
