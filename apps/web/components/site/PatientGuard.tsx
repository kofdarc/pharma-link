"use client";

import { createContext, useContext } from "react";
import { useRequireRole } from "@/lib/auth";
import type { User } from "@/types/api";

const PatientUserContext = createContext<User | null>(null);

/**
 * The signed-in patient, guaranteed.
 *
 * Only callable under `PatientGuard`, which does not render its children until
 * `/auth/me/` has come back with a CUSTOMER. That is what makes the non-null
 * return honest, and it is why the patient pages no longer need a fallback
 * identity to render against.
 */
export function usePatientUser(): User {
  const user = useContext(PatientUserContext);
  if (!user) throw new Error("usePatientUser must be used inside <PatientGuard>");
  return user;
}

/**
 * The signed-in patient, or null on a page that is open to everyone.
 *
 * For components shared between the patient area and the public site - the
 * shell chrome - which need to render either way.
 */
export function useMaybePatientUser(): User | null {
  return useContext(PatientUserContext);
}

/**
 * Gate for the patient area.
 *
 * The counterpart to `ProtectedLayout`, which does the same job for the
 * pharmacy, doctor, driver and admin areas. Without it these pages rendered for
 * anyone: signed out, the avatar and greeting fell back to fixture data, so the
 * app looked signed in as someone else entirely.
 */
export function PatientGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireRole(["CUSTOMER"]);

  if (loading || !user) {
    return (
      <div className="center-screen">
        <div className="skeleton-card" />
      </div>
    );
  }

  return <PatientUserContext.Provider value={user}>{children}</PatientUserContext.Provider>;
}
