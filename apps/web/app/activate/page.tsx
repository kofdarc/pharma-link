"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, setToken } from "@/lib/api-client";
import type { Doctor, User } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { BrandMark } from "@/components/ui/BrandMark";

/**
 * Zero-onboarding activation.
 *
 * The Order of Physicians roster is already loaded, so a doctor never fills in a profile.
 * They prove control of the licence + registered email pair, choose a password, and they
 * are prescribing within a minute.
 *
 * This route sits at /activate, outside /doctor/*, on purpose: the doctor has no account
 * yet, so it must not sit behind the doctor-role guard in app/doctor/layout.tsx.
 */
export default function DoctorActivationPage() {
  const router = useRouter();
  const [licenseNumber, setLicenseNumber] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiFetch<Doctor>("/doctors/activate/", {
        method: "POST",
        body: JSON.stringify({ license_number: licenseNumber.trim(), email: email.trim(), password })
      });
      // Activation creates the account; sign straight in so there is no second step.
      const session = await apiFetch<{ token: string; user: User }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password })
      });
      setToken(session.token);
      router.push("/doctor/prescriptions");
    } catch (exception) {
      setError((exception as ApiError).message || "Activation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <Link href="/" className="brand">
          <BrandMark />
          <span>PharmaLink</span>
        </Link>
        <h1>Activate your prescriber account</h1>
        <p className="muted">
          Your details are already on file from the Order of Physicians. There is nothing to fill in beyond
          confirming who you are and choosing a password.
        </p>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <form onSubmit={submit} className="stacked-form">
          <Field label="Licence number">
            <input value={licenseNumber} onChange={(event) => setLicenseNumber(event.target.value)} placeholder="LB-MD-00000" autoFocus />
          </Field>
          <Field label="Registered email" hint="The address the Order of Physicians holds for you.">
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field label="Choose a password">
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} />
          </Field>
          <Field label="Confirm password">
            <input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} minLength={8} />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? "Activating..." : "Activate and sign in"}
          </Button>
        </form>

        <p className="muted small">
          Already activated? <Link href="/login">Sign in</Link>.
        </p>
      </div>
    </div>
  );
}
