import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post, ApiError } from "../services/api";
import type { User } from "../types";
const AuthContext = createContext<{
  user: User | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
}>({
  user: null,
  loading: true,
  error: null,
  refresh: async () => {},
  logout: async () => {},
});
export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
  useEffect(() => {
    const expire = () => {
      client.setQueryData(["me"], null);
      client.invalidateQueries({ queryKey: ["me"] });
    };
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, [client]);
  return (
    <AuthContext.Provider
      value={{
        user: q.data ?? null,
        loading: q.isPending,
        error: q.error instanceof ApiError && q.error.status === 401 ? null : q.error,
        refresh: async () => {
          await client.cancelQueries();
          client.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" });
          await client.invalidateQueries({ queryKey: ["me"] });
        },
        logout: async () => {
          await post("/auth/logout");
          await client.cancelQueries();
          client.setQueryData(["me"], null);
          client.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export const useAuth = () => useContext(AuthContext);
