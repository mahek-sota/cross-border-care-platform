import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api, formatUsd } from "../lib/api";

export default function ProviderDetailPage() {
  const { providerId = "" } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["provider", providerId],
    queryFn: () => api.getProvider(providerId),
  });

  if (isLoading) return <p className="text-sm text-slate-500">Loading provider…</p>;
  if (isError || !data) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-700">This provider could not be found.</p>
        <Link to="/providers" className="text-sm text-slate-900 underline">
          Back to search
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/providers" className="text-sm text-slate-500 hover:text-slate-900">
          ← Search
        </Link>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">{data.name}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {data.city}, {data.country}
          {data.established_year && ` · established ${data.established_year}`}
          {data.bed_count && ` · ${data.bed_count} beds`}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-4">
        <Stat
          label="Rating"
          value={data.avg_rating ? `${Number(data.avg_rating).toFixed(1)} / 5` : "Unrated"}
        />
        <Stat label="Accreditations" value={data.accreditations.join(", ") || "None listed"} />
        <Stat label="Languages" value={data.languages.join(", ") || "—"} />
        <Stat
          label="Intl. patients"
          value={data.intl_patient_services ? "Supported" : "Not offered"}
        />
      </dl>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Specialties
        </h2>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {data.specialties.map((specialty) => (
            <span
              key={specialty}
              className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
            >
              {specialty}
            </span>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Procedures &amp; pricing
        </h2>
        {data.procedures.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No published pricing.</p>
        ) : (
          <div className="mt-3 overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Procedure</th>
                  <th className="px-4 py-2 font-medium">Price range (USD)</th>
                  <th className="px-4 py-2 font-medium">Typical stay</th>
                  <th className="px-4 py-2 font-medium">Wait time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.procedures.map((procedure) => (
                  <tr key={procedure.id}>
                    <td className="px-4 py-2">
                      <span className="font-medium text-slate-900">
                        {procedure.procedure_name}
                      </span>
                      <span className="ml-2 text-xs text-slate-400">
                        {procedure.procedure_code}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-slate-800">
                      {formatUsd(procedure.price_min_usd)} – {formatUsd(procedure.price_max_usd)}
                    </td>
                    <td className="px-4 py-2 text-slate-600">
                      {procedure.typical_stay_days != null
                        ? `${procedure.typical_stay_days} days`
                        : "—"}
                    </td>
                    <td className="px-4 py-2 text-slate-600">
                      {procedure.wait_time_days != null
                        ? `${procedure.wait_time_days} days`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{value}</dd>
    </div>
  );
}
