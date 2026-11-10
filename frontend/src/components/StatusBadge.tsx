import type { CaseStatus } from "../lib/api";

const STATUS_STYLES: Record<CaseStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-blue-100 text-blue-800",
  under_review: "bg-amber-100 text-amber-800",
  provider_matched: "bg-violet-100 text-violet-800",
  quoted: "bg-cyan-100 text-cyan-800",
  scheduled: "bg-indigo-100 text-indigo-800",
  completed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-red-100 text-red-800",
};

export default function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
