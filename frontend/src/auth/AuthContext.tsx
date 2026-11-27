import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";

export interface Me {
  id: number; username: string; full_name: string; role: string; role_label: string; title: string;
  email: string; business_unit: string; permissions: string[];
}
interface AuthState {
  user: Me | null; loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  can: (perm: string) => boolean;
}
const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!!getToken());

  useEffect(() => {
    if (!getToken()) return;
    api<Me>("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const h = () => setUser(null);
    window.addEventListener("modelguard:unauthorized", h);
    return () => window.removeEventListener("modelguard:unauthorized", h);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const r = await api<{ access_token: string; user: Me }>("/auth/login", { body: { username, password } });
    setToken(r.access_token);
    setUser(r.user);
  }, []);
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);
  const can = useCallback((perm: string) => !!user?.permissions.includes(perm), [user]);
  return <Ctx.Provider value={{ user, loading, login, logout, can }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
