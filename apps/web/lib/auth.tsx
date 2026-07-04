"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, clearToken } from "./api-client";
import type { User, UserRole } from "@/types/api";

export function useCurrentUser() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<User>("/auth/me/")
      .then(setUser)
      .catch(() => {
        clearToken();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  return { user, loading };
}

export function useRequireRole(roles: UserRole[]) {
  const router = useRouter();
  const state = useCurrentUser();

  useEffect(() => {
    if (state.loading) return;
    if (!state.user) router.replace("/login");
    else if (!roles.includes(state.user.role)) router.replace(state.user.role === "PLATFORM_ADMIN" ? "/admin" : "/pharmacy/dashboard");
  }, [roles, router, state.loading, state.user]);

  return state;
}

