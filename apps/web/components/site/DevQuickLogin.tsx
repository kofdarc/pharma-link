"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setToken } from "@/lib/api-client";
import { ROLE_HOME } from "@/lib/constants";
import type { User } from "@/types/api";
import { FormAlert } from "@/components/site/FormField";

// Matches apps/api/apps/pharmacies/management/commands/seed_poc.py - every seeded account
// shares this password (PASSWORD constant there). staff@cedarcare.test is PHARMACY_STAFF,
// the role gated on IsPharmacyUserWithActivePharmacy for pharmacy-side endpoints (sales,
// prescriptions/extract, inventory, ...) - the one to use for testing those flows.
const SEEDED_PASSWORD = "Password123!";

const DEV_ACCOUNTS = [
  { label: "Platform admin", email: "admin@healthconnect.dev" },
  { label: "Pharmacy owner (Cedar Care)", email: "owner@cedarcare.test" },
  { label: "Pharmacy staff (Cedar Care)", email: "staff@cedarcare.test" },
  { label: "Doctor", email: "rima.khalil@doctors.test" },
  { label: "Shopper", email: "shopper1@healthconnect.dev" },
  { label: "Driver", email: "karim@healthconnect.dev" }
];

export function DevQuickLogin() {
  const router = useRouter();
  const [loadingEmail, setLoadingEmail] = useState("");
  const [error, setError] = useState("");

  // Renders in local dev automatically. On a deployed build it only renders when
  // NEXT_PUBLIC_ENABLE_DEMO_LOGIN=true is set for that deployment - this signs in with a
  // password shared across every seeded account, so it must stay opt-in per-environment
  // rather than default-on for any production build.
  const isProductionBuild = process.env.NODE_ENV === "production";
  const demoLoginEnabled = process.env.NEXT_PUBLIC_ENABLE_DEMO_LOGIN === "true";
  if (isProductionBuild && !demoLoginEnabled) return null;

  async function loginAs(email: string) {
    setLoadingEmail(email);
    setError("");
    try {
      const session = await apiFetch<{ token: string; user: User }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email, password: SEEDED_PASSWORD })
      });
      setToken(session.token);
      router.push(ROLE_HOME[session.user.role] || "/home");
    } catch {
      setError(`Couldn't sign in as ${email} - is the DB seeded (manage.py seed_poc)?`);
      setLoadingEmail("");
    }
  }

  return (
    <div className="hc-dev-quick-login" style={{ marginTop: 24, paddingTop: 16, borderTop: "1px dashed var(--hc-line)" }}>
      <p className="hc-small" style={{ marginBottom: 8 }}>
        Demo accounts - quick sign in as a seeded role:
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {DEV_ACCOUNTS.map((account) => (
          <button
            key={account.email}
            type="button"
            className="hc-btn hc-btn-secondary hc-btn-sm"
            disabled={loadingEmail !== ""}
            onClick={() => loginAs(account.email)}
          >
            {loadingEmail === account.email ? "Signing in…" : account.label}
          </button>
        ))}
      </div>
      {error ? (
        <div style={{ marginTop: 8 }}>
          <FormAlert>{error}</FormAlert>
        </div>
      ) : null}
    </div>
  );
}
