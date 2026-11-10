import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./lib/auth";
import CaseDetailPage from "./pages/CaseDetailPage";
import CasesPage from "./pages/CasesPage";
import ComparePage from "./pages/ComparePage";
import LoginPage from "./pages/LoginPage";
import ProviderDetailPage from "./pages/ProviderDetailPage";
import ProvidersPage from "./pages/ProvidersPage";
import RegisterPage from "./pages/RegisterPage";

const NAV = [
  { to: "/providers", label: "Find providers" },
  { to: "/cases", label: "Cases" },
];

function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div className="flex items-center gap-6">
            <span className="text-sm font-semibold text-slate-900">Cross-Border Care</span>
            <nav className="flex items-center gap-4 text-sm">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    isActive
                      ? "font-medium text-slate-900"
                      : "text-slate-500 hover:text-slate-900"
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          {user && (
            <div className="flex items-center gap-4 text-sm">
              <span className="text-slate-600">
                {user.email} · <span className="text-slate-400">{user.role}</span>
              </span>
              <button
                onClick={() => logout()}
                className="rounded-md border border-slate-300 px-2 py-1 text-slate-700 hover:bg-slate-50"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}

/** Every signed-in page shares the shell; this keeps the route table readable. */
function Protected({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        path="/providers"
        element={
          <Protected>
            <ProvidersPage />
          </Protected>
        }
      />
      {/* Declared before /providers/:providerId so "compare" is not read as an id. */}
      <Route
        path="/providers/compare"
        element={
          <Protected>
            <ComparePage />
          </Protected>
        }
      />
      <Route
        path="/providers/:providerId"
        element={
          <Protected>
            <ProviderDetailPage />
          </Protected>
        }
      />

      <Route
        path="/cases"
        element={
          <Protected>
            <CasesPage />
          </Protected>
        }
      />
      <Route
        path="/cases/:caseId"
        element={
          <Protected>
            <CaseDetailPage />
          </Protected>
        }
      />

      <Route path="/" element={<Navigate to="/providers" replace />} />
      <Route path="*" element={<Navigate to="/providers" replace />} />
    </Routes>
  );
}
