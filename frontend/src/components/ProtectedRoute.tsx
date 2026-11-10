import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import type { UserRole } from "../lib/api";
import { useAuth } from "../lib/auth";

interface Props {
  children: ReactNode;
  /** When given, the route also requires one of these roles. */
  roles?: UserRole[];
}

export default function ProtectedRoute({ children, roles }: Props) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold text-slate-900">Not available</h1>
        <p className="mt-1 text-sm text-slate-600">
          Your account ({user.role}) does not have access to this page.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
