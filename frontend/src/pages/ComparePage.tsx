import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { api, formatPriceRange, type ProcedurePrice, type ProviderDetail } from "../lib/api";

/** Cheapest low-end price wins; providers without a price never win. */
function bestPriceId(providers: ProviderDetail[], procedureCode: string | null): string | null {
  if (!procedureCode) return null;
  let bestId: string | null = null;
  let bestValue = Number.POSITIVE_INFINITY;
  for (const provider of providers) {
    const price = provider.procedures.find((p) => p.procedure_code === procedureCode);
    if (!price) continue;
    const value = Number(price.price_min_usd);
    if (value < bestValue) {
      bestValue = value;
      bestId = provider.id;
    }
  }
  return bestId;
}

function priceFor(
  provider: ProviderDetail,
  procedureCode: string | null,
): ProcedurePrice | undefined {
  if (procedureCode) {
    return provider.procedures.find((p) => p.procedure_code === procedureCode);
  }
  return undefined;
}

export default function ComparePage() {
  const [searchParams] = useSearchParams();
  const ids = searchParams.getAll("ids");
  const procedureCode = searchParams.get("procedure_code");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["provider-compare", ids, procedureCode],
    queryFn: () => api.compareProviders(ids, procedureCode ?? undefined),
    enabled: ids.length >= 2,
  });

  if (ids.length < 2) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-700">Select at least two providers to compare.</p>
        <Link to="/providers" className="text-sm text-slate-900 underline">
          Back to search
        </Link>
      </div>
    );
  }

  if (isLoading) return <p className="text-sm text-slate-500">Loading comparison…</p>;
  if (isError || !data) {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-red-700">
          {(error as Error)?.message ?? "Could not load these providers."}
        </p>
        <Link to="/providers" className="text-sm text-slate-900 underline">
          Back to search
        </Link>
      </div>
    );
  }

  const providers = data.providers;
  const cheapestId = bestPriceId(providers, data.procedure_code);

  const rows: { label: string; render: (provider: ProviderDetail) => React.ReactNode }[] = [
    {
      label: "Location",
      render: (p) => `${p.city}, ${p.country}`,
    },
    {
      label: "Rating",
      render: (p) =>
        p.avg_rating ? `${Number(p.avg_rating).toFixed(1)} / 5` : <Muted>Unrated</Muted>,
    },
    {
      label: data.procedure_code ? `Price — ${data.procedure_code}` : "Price",
      render: (p) => {
        const price = priceFor(p, data.procedure_code);
        if (!price) return <Muted>Not offered</Muted>;
        return (
          <span className={p.id === cheapestId ? "font-semibold text-emerald-700" : undefined}>
            {formatPriceRange(price)}
            {p.id === cheapestId && <span className="ml-1 text-xs">lowest</span>}
          </span>
        );
      },
    },
    {
      label: "Typical stay",
      render: (p) => {
        const days = priceFor(p, data.procedure_code)?.typical_stay_days;
        return days != null ? `${days} days` : <Muted>—</Muted>;
      },
    },
    {
      label: "Wait time",
      render: (p) => {
        const days = priceFor(p, data.procedure_code)?.wait_time_days;
        return days != null ? `${days} days` : <Muted>—</Muted>;
      },
    },
    {
      label: "Accreditations",
      render: (p) => (p.accreditations.length ? p.accreditations.join(", ") : <Muted>None</Muted>),
    },
    {
      label: "Specialties",
      render: (p) => p.specialties.join(", ") || <Muted>—</Muted>,
    },
    {
      label: "Languages",
      render: (p) => p.languages.join(", ") || <Muted>—</Muted>,
    },
    {
      label: "Intl. patient services",
      render: (p) => (p.intl_patient_services ? "Yes" : <Muted>No</Muted>),
    },
    {
      label: "Beds",
      render: (p) => p.bed_count ?? <Muted>—</Muted>,
    },
    {
      label: "Established",
      render: (p) => p.established_year ?? <Muted>—</Muted>,
    },
  ];

  return (
    <div className="space-y-5">
      <div>
        <Link to="/providers" className="text-sm text-slate-500 hover:text-slate-900">
          ← Search
        </Link>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">
          Comparing {providers.length} providers
        </h1>
        {data.procedure_code ? (
          <p className="mt-1 text-sm text-slate-600">
            Prices shown for <span className="font-medium">{data.procedure_code}</span>.
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-600">
            No procedure selected, so no prices are shown. Pick one in the search filters to
            compare cost.
          </p>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="w-48 px-4 py-3 text-xs font-medium uppercase tracking-wide text-slate-500">
                &nbsp;
              </th>
              {providers.map((provider) => (
                <th key={provider.id} className="px-4 py-3 align-top">
                  <Link
                    to={`/providers/${provider.id}`}
                    className="font-medium text-slate-900 underline-offset-2 hover:underline"
                  >
                    {provider.name}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => (
              <tr key={row.label}>
                <th
                  scope="row"
                  className="px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-slate-500"
                >
                  {row.label}
                </th>
                {providers.map((provider) => (
                  <td key={provider.id} className="px-4 py-2.5 text-slate-800">
                    {row.render(provider)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-slate-400">{children}</span>;
}
