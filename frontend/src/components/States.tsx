interface LoadingProps {
  label?: string;
}

export function LoadingState({ label = "Loading analysis…" }: LoadingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="card flex items-center gap-3 text-sm text-ink-600"
    >
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink-300 border-t-signal-600" />
      {label}
    </div>
  );
}

interface ErrorProps {
  message: string;
  onRetry: () => void;
}

export function ErrorPanel({ message, onRetry }: ErrorProps) {
  return (
    <div role="alert" className="card border-red-300 bg-red-50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-red-800">Could not load the analysis</h2>
          <p className="mt-1 text-sm text-red-700">{message}</p>
        </div>
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="card text-sm text-ink-600" role="status">
      {message}
    </div>
  );
}
