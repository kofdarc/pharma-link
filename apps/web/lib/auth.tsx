"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AUTH_EXPIRED_EVENT, apiFetch, clearToken, getToken } from "./api-client";
import { ROLE_HOME } from "./constants";
import { clearBasket } from "./basket";
import { clearPatientState } from "./patient/store";
import type { User, UserRole } from "@/types/api";

/**
 * End the session and leave nothing of this patient behind on the device.
 *
 * Dropping the token alone is not enough: prescriptions, orders, addresses and
 * the basket live in localStorage, so without this the next person to open the
 * app on a shared device still sees the previous one's records.
 */
export function signOut() {
  clearToken();
  clearPatientState();
  clearBasket();
}

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

/**
 * The signed-in user, if there happens to be one.
 *
 * For pages that are open to everyone but adapt when someone is signed in (the
 * public header, medication search). Unlike `useCurrentUser` it makes no
 * request at all without a token, so anonymous visitors do not pay for a 401 on
 * every page they open.
 */
export function useOptionalUser() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    apiFetch<User>("/auth/me/")
      .then((value) => {
        if (!cancelled) setUser(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return user;
}

export function useRequireRole(roles: UserRole[]) {
  const router = useRouter();
  const pathname = usePathname();
  const state = useCurrentUser();

  useEffect(() => {
    if (state.loading) return;
    // Signed out: send them to sign in, but remember where they were headed so
    // login can drop them back here (e.g. cart -> checkout -> login -> checkout).
    if (!state.user) {
      const next = pathname && pathname !== "/login" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    } else if (!roles.includes(state.user.role)) {
      router.replace(ROLE_HOME[state.user.role] || "/login");
    }
  }, [roles, router, pathname, state.loading, state.user]);

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

