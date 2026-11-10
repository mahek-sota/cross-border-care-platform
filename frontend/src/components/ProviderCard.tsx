import { Link } from "react-router-dom";

import { formatPriceRange, type Provider } from "../lib/api";

interface Props {
  provider: Provider;
  selected: boolean;
  disabled: boolean;
  onToggleCompare: () => void;
}

export default function ProviderCard({ provider, selected, disabled, onToggleCompare }: Props) {
  const price = provider.matched_procedure;

  return (
    <li
      className={`rounded-lg border bg-white p-4 transition ${
        selected ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to={`/providers/${provider.id}`}
            className="font-medium text-slate-900 underline-offset-2 hover:underline"
          >
            {provider.name}
          </Link>
          <p className="mt-0.5 text-sm text-slate-600">
            {provider.city}, {provider.country}
            {provider.established_year && (
              <span className="text-slate-400"> · est. {provider.established_year}</span>
            )}
          </p>
        </div>

        <div className="shrink-0 text-right">
          {provider.avg_rating ? (
            <p className="text-sm font-medium text-slate-900">
              {Number(provider.avg_rating).toFixed(1)}
              <span className="text-slate-400"> / 5</span>
            </p>
          ) : (
            <p className="text-xs text-slate-400">Unrated</p>
          )}
          {price && (
            <p className="mt-1 text-sm font-medium text-slate-900">
              {formatPriceRange(price)}
            </p>
          )}
        </div>
      </div>

      {price && (
        <p className="mt-2 text-xs text-slate-500">
          {price.procedure_name}
          {price.typical_stay_days !== null && ` · ${price.typical_stay_days}-day stay`}
          {price.wait_time_days !== null && ` · ${price.wait_time_days}-day wait`}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {provider.specialties.slice(0, 4).map((specialty) => (
          <span
            key={specialty}
            className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
          >
            {specialty}
          </span>
        ))}
        {provider.accreditations.map((accreditation) => (
          <span
            key={accreditation}
            className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800"
          >
            {accreditation}
          </span>
        ))}
        {provider.intl_patient_services && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-800">
            Intl. patient services
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
        <p className="text-xs text-slate-500">
          Languages: {provider.languages.join(", ") || "—"}
        </p>
        <label
          className={`flex items-center gap-2 text-xs ${
            disabled ? "cursor-not-allowed text-slate-400" : "cursor-pointer text-slate-700"
          }`}
          title={disabled ? "Comparison is limited to 4 providers" : undefined}
        >
          <input
            type="checkbox"
            checked={selected}
            disabled={disabled}
            onChange={onToggleCompare}
            className="rounded border-slate-300"
          />
          Compare
        </label>
      </div>
    </li>
  );
}
