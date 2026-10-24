export type View = "overview" | "explorer" | "errors" | "quality";

interface Props {
  view: View;
  onChange: (view: View) => void;
}

const TABS: { id: View; label: string; description: string }[] = [
  { id: "overview", label: "Overview", description: "Headline accuracy, chart, insights and data table" },
  { id: "explorer", label: "Forecast Explorer", description: "Every forecast vintage behind one delivery interval" },
  { id: "errors", label: "Error Analysis", description: "Error charts, heatmap and reliability metrics" },
  { id: "quality", label: "Data Quality", description: "Sources, completeness, cache and limitations" },
];

export default function TabNav({ view, onChange }: Props) {
  return (
    <nav aria-label="Sections" className="border-b border-ink-200">
      <div role="tablist" aria-label="Analysis sections" className="flex gap-1 overflow-x-auto">
        {TABS.map((tab) => {
          const active = tab.id === view;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`panel-${tab.id}`}
              title={tab.description}
              onClick={() => onChange(tab.id)}
              className={
                active
                  ? "whitespace-nowrap border-b-2 border-signal-600 px-3 py-2 text-sm font-semibold text-signal-700"
                  : "whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900"
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
