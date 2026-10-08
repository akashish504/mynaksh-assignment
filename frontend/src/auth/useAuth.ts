import { createContext, useContext } from "react";

import type { Me } from "../api/types";

export interface AuthState {
  me: Me | null;
  // True while the saved token is being checked on first load.
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
  // Call after the profile changes so the rest of the app sees it.
  setMe: (me: Me) => void;
}

export const AuthContext = createContext<AuthState | null>(null);

// Every page reads who is logged in through this hook.
export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return state;
}
