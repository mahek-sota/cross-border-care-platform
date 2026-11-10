import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import StatusBadge from "../components/StatusBadge";
import { api, type CaseStatus } from "../lib/api";
import { useAuth } from "../lib/auth";

/** Mirrors ALLOWED_TRANSITIONS in backend/app/services/cases.py. */
const NEXT_STATUSES: Record<CaseStatus, CaseStatus[]> = {
  draft: ["submitted", "cancelled"],
  submitted: ["under_review", "cancelled"],
  under_review: ["provider_matched", "cancelled"],
  provider_matched: ["quoted", "cancelled"],
  quoted: ["scheduled", "cancelled"],
  scheduled: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
};

const PATIENT_TRANSITIONS: CaseStatus[] = ["submitted", "cancelled"];

export default function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId) });
  const eventsQuery = useQuery({
    queryKey: ["case", caseId, "events"],
    queryFn: () => api.listCaseEvents(caseId),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["case", caseId] });
    queryClient.invalidateQueries({ queryKey: ["cases"] });
  }

  const changeStatus = useMutation({
    mutationFn: (status: CaseStatus) => api.updateCaseStatus(caseId, status),
    onSuccess: invalidate,
  });
  const claim = useMutation({ mutationFn: () => api.claimCase(caseId), onSuccess: invalidate });

  if (caseQuery.isLoading) return <p className="text-sm text-slate-500">Loading case…</p>;
  if (caseQuery.isError || !caseQuery.data) {
    return (
      <div>
        <p className="text-sm text-slate-700">
          This case is not available. It may not exist, or it may belong to someone else.
        </p>
        <Link to="/cases" className="mt-3 inline-block text-sm text-slate-900 underline">
          Back to cases
        </Link>
      </div>
    );
  }

  const record = caseQuery.data;
  const isPatient = user?.role === "patient";
  const isCoordinator = user?.role === "coordinator";
  const claimedByMe = record.coordinator_id === user?.id;

  // A coordinator must claim a case before driving it; the server enforces this too.
  const canChangeStatus = isPatient || user?.role === "admin" || (isCoordinator && claimedByMe);
  const available = NEXT_STATUSES[record.status].filter(
    (status) => !isPatient || PATIENT_TRANSITIONS.includes(status),
  );

  return (
    <div className="space-y-8">
      <div>
        <Link to="/cases" className="text-sm text-slate-500 hover:text-slate-900">
          ← Cases
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-slate-900">{record.procedure_code}</h1>
          <StatusBadge status={record.status} />
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Target countries: {record.target_countries.join(", ") || "—"} · Opened{" "}
          {new Date(record.created_at).toLocaleString()}
        </p>
      </div>

      <section className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-4">
        {isCoordinator && !record.coordinator_id && (
          <button
            onClick={() => claim.mutate()}
            disabled={claim.isPending}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {claim.isPending ? "Claiming…" : "Claim this case"}
          </button>
        )}

        {canChangeStatus && available.length > 0 ? (
          available.map((status) => (
            <button
              key={status}
              onClick={() => changeStatus.mutate(status)}
              disabled={changeStatus.isPending}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            >
              Move to {status.replace(/_/g, " ")}
            </button>
          ))
        ) : (
          <p className="text-sm text-slate-500">
            {available.length === 0
              ? "This case has reached a final state."
              : "Claim the case to move it forward."}
          </p>
        )}

        {changeStatus.isError && (
          <p role="alert" className="w-full text-sm text-red-700">
            {(changeStatus.error as Error).message}
          </p>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Activity
        </h2>
        {eventsQuery.isLoading ? (
          <p className="mt-2 text-sm text-slate-500">Loading activity…</p>
        ) : (
          <ol className="mt-3 space-y-3 border-l border-slate-200 pl-4">
            {eventsQuery.data?.map((event) => (
              <li key={event.id} className="text-sm">
                <span className="font-medium text-slate-900">
                  {event.event_type.replace(/_/g, " ")}
                </span>
                <span className="ml-2 text-slate-500">
                  {new Date(event.created_at).toLocaleString()}
                </span>
                {Object.keys(event.payload).length > 0 && (
                  <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-600">
                    {JSON.stringify(event.payload, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
