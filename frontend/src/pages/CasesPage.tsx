import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import StatusBadge from "../components/StatusBadge";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function CasesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [procedureCode, setProcedureCode] = useState("");
  const [countries, setCountries] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn: () => api.listCases({ limit: 50 }),
  });

  const createCase = useMutation({
    mutationFn: api.createCase,
    onSuccess: () => {
      setProcedureCode("");
      setCountries("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createCase.mutate({
      procedure_code: procedureCode.trim(),
      target_countries: countries
        .split(",")
        .map((code) => code.trim())
        .filter(Boolean),
    });
  }

  const isPatient = user?.role === "patient";

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">
          {isPatient ? "My cases" : "Case queue"}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {isPatient
            ? "Cases you have opened, and where each one stands."
            : "Cases assigned to you, plus unclaimed cases waiting for a coordinator."}
        </p>
      </header>

      {isPatient && (
        <form
          onSubmit={handleCreate}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4"
        >
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Procedure code</span>
            <input
              required
              value={procedureCode}
              onChange={(e) => setProcedureCode(e.target.value)}
              placeholder="TKR-001"
              className="mt-1 w-44 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Target countries</span>
            <input
              value={countries}
              onChange={(e) => setCountries(e.target.value)}
              placeholder="IN, TH"
              className="mt-1 w-48 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
            />
          </label>
          <button
            type="submit"
            disabled={createCase.isPending}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {createCase.isPending ? "Creating…" : "New case"}
          </button>
          {error && (
            <p role="alert" className="w-full text-sm text-red-700">
              {error}
            </p>
          )}
        </form>
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading cases…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          No cases yet.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Procedure</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Target countries</th>
                <th className="px-4 py-2 font-medium">Coordinator</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((caseRow) => (
                <tr key={caseRow.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link
                      to={`/cases/${caseRow.id}`}
                      className="font-medium text-slate-900 underline-offset-2 hover:underline"
                    >
                      {caseRow.procedure_code}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={caseRow.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {caseRow.target_countries.join(", ") || "—"}
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {caseRow.coordinator_id ? "Assigned" : "Unassigned"}
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {new Date(caseRow.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
            {data.meta.total} case{data.meta.total === 1 ? "" : "s"}
          </p>
        </div>
      )}
    </div>
  );
}
