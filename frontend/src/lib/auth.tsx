import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api, bootstrapSession, hasSession, onAuthChange, type Me } from "./api";

interface AuthContextValue {
  user: Me | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    full_name: string;
    country?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  // Until the stored refresh token has been exchanged we cannot tell a logged-out
  // visitor from a reloading one, so hold the routes back rather than flashing login.
  const [bootstrapped, setBootstrapped] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);

  useEffect(() => {
    bootstrapSession().finally(() => setBootstrapped(true));
    return onAuthChange(() => setSessionKey((key) => key + 1));
  }, []);

  const { data, isLoading } = useQuery({
    queryKey: ["me", sessionKey],
    queryFn: api.me,
    enabled: bootstrapped && hasSession(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const value: AuthContextValue = {
    user: data ?? null,
    isLoading: !bootstrapped || (hasSession() && isLoading),
    async login(email, password) {
      await api.login(email, password);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    async register(input) {
      await api.register(input);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    async logout() {
      await api.logout();
      queryClient.clear();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
