// Holds who is logged in. Pages read it through the useAuth() hook.

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import type { Me } from "../api/types";
import { AuthContext } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(getToken() !== null);

  const logout = useCallback(() => {
    setToken(null);
    setMe(null);
  }, []);

  // An expired token anywhere in the app logs the user out.
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  // On first load, a saved token is used to fetch the user.
  useEffect(() => {
    if (getToken() === null) {
      return;
    }
    api
      .getMe()
      .then(setMe)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  async function startSession(token: string) {
    setToken(token);
    setMe(await api.getMe());
  }

  async function login(email: string, password: string) {
    const result = await api.login(email, password);
    await startSession(result.access_token);
  }

  async function signup(email: string, password: string) {
    const result = await api.signup(email, password);
    await startSession(result.access_token);
  }

  return (
    <AuthContext.Provider value={{ me, loading, login, signup, logout, setMe }}>
      {children}
    </AuthContext.Provider>
  );
}
