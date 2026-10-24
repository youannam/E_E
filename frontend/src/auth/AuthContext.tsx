// Keeps track of who is logged in and shares it with every page.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import type { Account, TokenResponse } from "../api/types";

interface AuthState {
  account: Account | null;
  checking: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: (reason?: string) => void;
  notice: string | null;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const [notice, setNotice] = useState<string | null>(null);

  const logout = useCallback((reason?: string) => {
    setToken(null);
    setAccount(null);
    setNotice(reason ?? null);
  }, []);

  // When any request gets 401 (expired token), go back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => logout("Your session has expired. Please log in again."));
  }, [logout]);

  // After a page reload, check whether the saved token is still valid.
  useEffect(() => {
    if (!getToken()) return;
    api
      .get<Account>("/auth/me")
      .then(setAccount)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.post<TokenResponse>("/auth/login", { username, password });
    setToken(result.access_token);
    setAccount(result.account);
    setNotice(null);
  }, []);

  return (
    <AuthContext.Provider value={{ account, checking, login, logout, notice }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
