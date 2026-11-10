import type { FacetValue } from "../lib/api";

interface Props {
  label: string;
  values: FacetValue[];
  selected: string[];
  onToggle: (value: string) => void;
  /** Collapse to this many chips until the user asks for more. */
  limit?: number;
}

export default function FacetChips({ label, values, selected, onToggle, limit }: Props) {
  if (values.length === 0) return null;
  const visible = limit ? values.slice(0, limit) : values;

  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {visible.map((facet) => {
          const isSelected = selected.includes(facet.value);
          return (
            <button
              key={facet.value}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onToggle(facet.value)}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                isSelected
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:border-slate-400"
              }`}
            >
              {facet.value}
              <span className={isSelected ? "ml-1 text-slate-300" : "ml-1 text-slate-400"}>
                {facet.count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
