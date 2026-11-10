import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import FacetChips from "../components/FacetChips";
import ProviderCard from "../components/ProviderCard";
import { api, type ProviderSearchParams, type ProviderSort } from "../lib/api";

const MAX_COMPARE = 4;
const PAGE_SIZE = 20;

const SORT_OPTIONS: { value: ProviderSort; label: string }[] = [
  { value: "relevance", label: "Best match" },
  { value: "price", label: "Lowest price" },
  { value: "rating", label: "Highest rated" },
  { value: "name", label: "Name (A–Z)" },
];

export default function ProvidersPage() {
  const navigate = useNavigate();
  // Filters live in the URL so a search can be linked, bookmarked, and survives reload.
  const [searchParams, setSearchParams] = useSearchParams();

  const q = searchParams.get("q") ?? "";
  const countries = searchParams.getAll("country");
  const specialties = searchParams.getAll("specialty");
  const languages = searchParams.getAll("language");
  const procedureCode = searchParams.get("procedure_code") ?? "";
  const maxPrice = searchParams.get("max_price_usd") ?? "";
  const minRating = searchParams.get("min_rating") ?? "";
  const intlOnly = searchParams.get("intl_patient_services") === "true";
  const sort = (searchParams.get("sort") as ProviderSort) ?? "relevance";
  const offset = Number(searchParams.get("offset") ?? 0);

  // The text box is local so typing does not rewrite history on every keystroke;
  // it is committed to the URL on submit.
  const [queryDraft, setQueryDraft] = useState(q);
  useEffect(() => setQueryDraft(q), [q]);

  const [compareIds, setCompareIds] = useState<string[]>([]);

  function update(changes: Record<string, string | string[] | null>, resetPaging = true) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (value === null || value === "") continue;
      if (Array.isArray(value)) value.forEach((entry) => next.append(key, entry));
      else next.set(key, value);
    }
    if (resetPaging) next.delete("offset");
    setSearchParams(next, { replace: true });
  }

  function toggle(key: string, value: string) {
    const current = searchParams.getAll(key);
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value];
    update({ [key]: next });
  }

  const params: ProviderSearchParams = {
    q: q || undefined,
    country: countries.length ? countries : undefined,
    specialty: specialties.length ? specialties : undefined,
    language: languages.length ? languages : undefined,
    procedure_code: procedureCode || undefined,
    max_price_usd: maxPrice ? Number(maxPrice) : undefined,
    min_rating: minRating ? Number(minRating) : undefined,
    intl_patient_services: intlOnly ? true : undefined,
    sort,
    limit: PAGE_SIZE,
    offset,
  };

  const facetsQuery = useQuery({ queryKey: ["provider-facets"], queryFn: api.providerFacets });
  const searchQuery = useQuery({
    queryKey: ["providers", params],
    queryFn: () => api.searchProviders(params),
    // Keep the previous page on screen while the next loads, instead of flashing empty.
    placeholderData: keepPreviousData,
  });

  function toggleCompare(providerId: string) {
    setCompareIds((current) =>
      current.includes(providerId)
        ? current.filter((id) => id !== providerId)
        : current.length >= MAX_COMPARE
          ? current
          : [...current, providerId],
    );
  }

  const facets = facetsQuery.data;
  const results = searchQuery.data;
  const total = results?.meta.total ?? 0;
  const hasFilters =
    Boolean(q || procedureCode || maxPrice || minRating || intlOnly) ||
    countries.length > 0 ||
    specialties.length > 0 ||
    languages.length > 0;

  return (
    <div className="space-y-6 pb-24">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Find a provider</h1>
        <p className="mt-1 text-sm text-slate-600">
          Search hospitals abroad by procedure, price, specialty, and accreditation.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          update({ q: queryDraft.trim() });
        }}
        className="flex gap-2"
      >
        <input
          value={queryDraft}
          onChange={(event) => setQueryDraft(event.target.value)}
          placeholder="Hospital name, specialty, or city — typos are fine"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
        />
        <button
          type="submit"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Search
        </button>
      </form>

      <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
        <aside className="space-y-5 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Filters</h2>
            {hasFilters && (
              <button
                type="button"
                onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
                className="text-xs text-slate-500 underline hover:text-slate-900"
              >
                Clear all
              </button>
            )}
          </div>

          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Procedure
            </span>
            <select
              value={procedureCode}
              onChange={(event) => update({ procedure_code: event.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-900"
            >
              <option value="">Any procedure</option>
              {facets?.procedures.map((facet) => (
                <option key={facet.value} value={facet.value}>
                  {facet.value} ({facet.count})
                </option>
              ))}
            </select>
            {!procedureCode && (
              <span className="mt-1 block text-xs text-slate-500">
                Pick one to compare prices and sort by cost.
              </span>
            )}
          </label>

          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Max price (USD)
            </span>
            <input
              type="number"
              min={0}
              step={500}
              value={maxPrice}
              onChange={(event) => update({ max_price_usd: event.target.value })}
              placeholder="No limit"
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-900"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Minimum rating
            </span>
            <select
              value={minRating}
              onChange={(event) => update({ min_rating: event.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-900"
            >
              <option value="">Any rating</option>
              <option value="4.5">4.5+</option>
              <option value="4">4.0+</option>
              <option value="3.5">3.5+</option>
            </select>
          </label>

          <FacetChips
            label="Country"
            values={facets?.countries ?? []}
            selected={countries}
            onToggle={(value) => toggle("country", value)}
          />
          <FacetChips
            label="Specialty"
            values={facets?.specialties ?? []}
            selected={specialties}
            onToggle={(value) => toggle("specialty", value)}
            limit={10}
          />
          <FacetChips
            label="Language"
            values={facets?.languages ?? []}
            selected={languages}
            onToggle={(value) => toggle("language", value)}
            limit={8}
          />

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={intlOnly}
              onChange={(event) =>
                update({ intl_patient_services: event.target.checked ? "true" : null })
              }
              className="rounded border-slate-300"
            />
            International patient services
          </label>
        </aside>

        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600">
              {searchQuery.isLoading
                ? "Searching…"
                : `${total} provider${total === 1 ? "" : "s"}`}
            </p>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Sort
              <select
                value={sort}
                onChange={(event) => update({ sort: event.target.value })}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm outline-none focus:border-slate-900"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {sort === "price" && !procedureCode && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Choose a procedure to sort by price — without one there is no single price
              to rank on, so these are ordered by rating.
            </p>
          )}

          {searchQuery.isError && (
            <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {(searchQuery.error as Error).message}
            </p>
          )}

          {results && results.items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 p-10 text-center">
              <p className="text-sm text-slate-600">No providers match these filters.</p>
              {hasFilters && (
                <button
                  type="button"
                  onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
                  className="mt-2 text-sm text-slate-900 underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <ul className="space-y-3">
              {results?.items.map((provider) => (
                <ProviderCard
                  key={provider.id}
                  provider={provider}
                  selected={compareIds.includes(provider.id)}
                  disabled={
                    !compareIds.includes(provider.id) && compareIds.length >= MAX_COMPARE
                  }
                  onToggleCompare={() => toggleCompare(provider.id)}
                />
              ))}
            </ul>
          )}

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() =>
                  update({ offset: String(Math.max(0, offset - PAGE_SIZE)) }, false)
                }
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-slate-500">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <button
                type="button"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => update({ offset: String(offset + PAGE_SIZE) }, false)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </section>
      </div>

      {compareIds.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 border-t border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
            <p className="text-sm text-slate-700">
              {compareIds.length} selected
              {compareIds.length >= MAX_COMPARE && (
                <span className="ml-2 text-xs text-slate-500">(maximum {MAX_COMPARE})</span>
              )}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setCompareIds([])}
                className="text-sm text-slate-600 underline"
              >
                Clear
              </button>
              <button
                type="button"
                disabled={compareIds.length < 2}
                title={compareIds.length < 2 ? "Select at least two providers" : undefined}
                onClick={() => {
                  const query = new URLSearchParams();
                  compareIds.forEach((id) => query.append("ids", id));
                  if (procedureCode) query.set("procedure_code", procedureCode);
                  navigate(`/providers/compare?${query}`);
                }}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                Compare
              </button>
            </div>
          </div>
        </div>
      )}

      <p className="text-center text-xs text-slate-400">
        <Link to="/cases" className="underline">
          Back to my cases
        </Link>
      </p>
    </div>
  );
}
