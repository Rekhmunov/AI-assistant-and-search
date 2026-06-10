import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "./api";

export type AdminRole = "owner" | "support" | "marketing";

export interface AdminUser {
  id: string;
  email: string;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface AuthState {
  admin: AdminUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (permission: string) => boolean;
}

const PERMS: Record<AdminRole, Set<string>> = {
  owner: new Set([
    "dashboard:read",
    "broadcasts:read",
    "broadcasts:write",
    "users:read",
    "users:write",
    "payments:read",
    "payments:write",
    "settings:read",
    "settings:write",
    "legal:read",
    "legal:write",
    "audit:read",
    "admins:read",
    "admins:write",
    "support:read",
    "support:write",
    "blog:read",
    "blog:write",
  ]),
  support: new Set([
    "dashboard:read",
    "users:read",
    "users:write",
    "payments:read",
    "payments:write",
    "support:read",
    "support:write",
    "audit:read",
  ]),
  marketing: new Set([
    "dashboard:read",
    "broadcasts:read",
    "broadcasts:write",
    "blog:read",
    "blog:write",
    "audit:read",
  ]),
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [admin, setAdmin] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await apiFetch<AdminUser>("/api/admin/auth/me");
      setAdmin(me);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAdmin(null);
      } else {
        setAdmin(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiFetch<{ ok: boolean; admin: AdminUser }>("/api/admin/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAdmin(res.admin);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/admin/auth/logout", { method: "POST" });
    } finally {
      setAdmin(null);
    }
  }, []);

  const can = useCallback(
    (permission: string) => {
      if (!admin) return false;
      return PERMS[admin.role]?.has(permission) ?? false;
    },
    [admin],
  );

  const value = useMemo(
    () => ({ admin, loading, login, logout, refresh, can }),
    [admin, loading, login, logout, refresh, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
