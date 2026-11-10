/**
 * Typed API client.
 *
 * The access token is held in memory only; the refresh token goes to localStorage so
 * a page reload can recover a session. On a 401 the client transparently refreshes
 * once and replays the request -- and because the backend rotates refresh tokens,
 * concurrent 401s share a single in-flight refresh rather than racing and revoking
 * each other's token.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REFRESH_TOKEN_KEY = "cbcare.refresh_token";

export type UserRole = "patient" | "coordinator" | "admin";

export type CaseStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "provider_matched"
  | "quoted"
  | "scheduled"
  | "completed"
  | "cancelled";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: string;
}

export interface PatientProfile {
  id: string;
  user_id: string;
  full_name: string;
  dob: string | null;
  country: string | null;
  phone: string | null;
  preferred_language: string | null;
}

export interface Me {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  profile: PatientProfile | null;
}

export interface Case {
  id: string;
  patient_id: string;
  coordinator_id: string | null;
  procedure_code: string;
  status: CaseStatus;
  target_countries: string[];
  created_at: string;
  updated_at: string;
}

export interface CasePage {
  items: Case[];
  meta: { total: number; limit: number; offset: number };
}

export interface CaseEvent {
  id: string;
  case_id: string;
  actor_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProcedurePrice {
  id: string;
  procedure_code: string;
  procedure_name: string;
  price_min_usd: string;
  price_max_usd: string;
  typical_stay_days: number | null;
  wait_time_days: number | null;
}

export interface Provider {
  id: string;
  name: string;
  country: string;
  city: string;
  specialties: string[];
  accreditations: string[];
  languages: string[];
  avg_rating: string | null;
  bed_count: number | null;
  intl_patient_services: boolean;
  latitude: string | null;
  longitude: string | null;
  established_year: number | null;
  /** Only set when the search filtered by procedure_code. */
  matched_procedure: ProcedurePrice | null;
}

export interface ProviderDetail extends Provider {
  procedures: ProcedurePrice[];
}

export interface ProviderPage {
  items: Provider[];
  meta: { total: number; limit: number; offset: number };
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface ProviderFacets {
  countries: FacetValue[];
  specialties: FacetValue[];
  languages: FacetValue[];
  accreditations: FacetValue[];
  procedures: FacetValue[];
}

export interface ProviderComparison {
  procedure_code: string | null;
  providers: ProviderDetail[];
}

export type ProviderSort = "relevance" | "price" | "rating" | "name";

export interface ProviderSearchParams {
  q?: string;
  country?: string[];
  specialty?: string[];
  language?: string[];
  accreditation?: string[];
  procedure_code?: string;
  max_price_usd?: number;
  min_rating?: number;
  intl_patient_services?: boolean;
  sort?: ProviderSort;
  limit?: number;
  offset?: number;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
const authChangeListeners = new Set<() => void>();

export function onAuthChange(listener: () => void): () => void {
  authChangeListeners.add(listener);
  return () => authChangeListeners.delete(listener);
}

function notifyAuthChange() {
  authChangeListeners.forEach((listener) => listener());
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: TokenPair | null) {
  accessToken = tokens?.access_token ?? null;
  if (tokens) {
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
  notifyAuthChange();
}

export function hasSession(): boolean {
  return accessToken !== null || getRefreshToken() !== null;
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg ?? "invalid").join("; ");
    }
  } catch {
    /* fall through to the status text */
  }
  return response.statusText || `Request failed (${response.status})`;
}

/** Exchange the stored refresh token for a new pair. At most one runs at a time. */
async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;

    const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      setTokens(null);
      return false;
    }
    setTokens((await response.json()) as TokenPair);
    return true;
  })().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Internal: prevents an infinite refresh loop. */
  retryOnUnauthorized?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, retryOnUnauthorized = true } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retryOnUnauthorized) {
    if (await refreshSession()) {
      return request<T>(path, { ...options, retryOnUnauthorized: false });
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --------------------------------------------------------------------------- //
// Endpoints
// --------------------------------------------------------------------------- //

export const api = {
  async login(email: string, password: string): Promise<TokenPair> {
    const tokens = await request<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      retryOnUnauthorized: false,
    });
    setTokens(tokens);
    return tokens;
  },

  async register(input: {
    email: string;
    password: string;
    full_name: string;
    country?: string;
  }): Promise<TokenPair> {
    const tokens = await request<TokenPair>("/api/v1/auth/register", {
      method: "POST",
      body: {
        email: input.email,
        password: input.password,
        profile: { full_name: input.full_name, country: input.country || null },
      },
      retryOnUnauthorized: false,
    });
    setTokens(tokens);
    return tokens;
  },

  async logout(): Promise<void> {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      // A failed logout must still clear the client; the token expires on its own.
      await request<void>("/api/v1/auth/logout", {
        method: "POST",
        body: { refresh_token: refreshToken },
      }).catch(() => undefined);
    }
    setTokens(null);
  },

  me: () => request<Me>("/api/v1/auth/me"),

  listCases: (params: { status?: CaseStatus; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    const suffix = query.toString() ? `?${query}` : "";
    return request<CasePage>(`/api/v1/cases${suffix}`);
  },

  getCase: (caseId: string) => request<Case>(`/api/v1/cases/${caseId}`),

  listCaseEvents: (caseId: string) => request<CaseEvent[]>(`/api/v1/cases/${caseId}/events`),

  createCase: (input: { procedure_code: string; target_countries: string[] }) =>
    request<Case>("/api/v1/cases", { method: "POST", body: input }),

  updateCaseStatus: (caseId: string, status: CaseStatus, reason?: string) =>
    request<Case>(`/api/v1/cases/${caseId}/status`, {
      method: "PATCH",
      body: { status, reason: reason ?? null },
    }),

  claimCase: (caseId: string) =>
    request<Case>(`/api/v1/cases/${caseId}/assign`, { method: "POST", body: {} }),

  searchProviders: (params: ProviderSearchParams = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === "" || value === null) continue;
      // Repeated keys, not comma-joined: FastAPI reads list[str] query params that way.
      if (Array.isArray(value)) {
        value.forEach((entry) => query.append(key, entry));
      } else {
        query.set(key, String(value));
      }
    }
    const suffix = query.toString() ? `?${query}` : "";
    return request<ProviderPage>(`/api/v1/providers${suffix}`);
  },

  getProvider: (providerId: string) =>
    request<ProviderDetail>(`/api/v1/providers/${providerId}`),

  providerFacets: () => request<ProviderFacets>("/api/v1/providers/facets"),

  compareProviders: (providerIds: string[], procedureCode?: string) => {
    const query = new URLSearchParams();
    providerIds.forEach((id) => query.append("ids", id));
    if (procedureCode) query.set("procedure_code", procedureCode);
    return request<ProviderComparison>(`/api/v1/providers/compare?${query}`);
  },
};

/** Prices arrive as decimal strings to avoid float rounding; format for display. */
export function formatUsd(value: string | null): string {
  if (value === null) return "—";
  const amount = Number(value);
  if (Number.isNaN(amount)) return "—";
  return amount.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function formatPriceRange(price: ProcedurePrice | null | undefined): string {
  if (!price) return "—";
  return `${formatUsd(price.price_min_usd)} – ${formatUsd(price.price_max_usd)}`;
}

/** Restore a session from the stored refresh token on app start. */
export async function bootstrapSession(): Promise<boolean> {
  if (accessToken) return true;
  if (!getRefreshToken()) return false;
  return refreshSession();
}
