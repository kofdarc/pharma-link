"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AUTH_EXPIRED_EVENT, apiFetch, clearToken } from "./api-client";
import { ROLE_HOME } from "./constants";
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
    else if (!roles.includes(state.user.role)) router.replace(ROLE_HOME[state.user.role] || "/login");
  }, [roles, router, state.loading, state.user]);

  // A 401 on some later request (not the initial /auth/me/ load) means the token expired
  // mid-session. Redirect with a flag so /login can explain why, instead of the page just
  // silently failing to load data.
  useEffect(() => {
    function onExpired() {
      router.replace("/login?expired=1");
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [router]);

  return state;
}

