"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, setToken } from "@/lib/api-client";
import type { User } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

/** Shopper self-signup. Only the CUSTOMER role can be self-assigned. */
export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await apiFetch<{ token: string; user: User }>("/auth/register/", {
        method: "POST",
        body: JSON.stringify(form)
      });
      setToken(session.token);
      router.push("/shop/addresses");
    } catch (exception) {
      const apiError = exception as ApiError;
      const details = apiError.details as Record<string, string[]> | undefined;
      const firstField = details ? Object.values(details)[0] : undefined;
      setError(Array.isArray(firstField) ? firstField[0] : apiError.message || "Could not create the account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>PharmaLink</span>
        </Link>
        <h1>Create your account</h1>
        <p className="muted">Search every connected pharmacy at once, order, and set up repeat refills.</p>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <form onSubmit={submit} className="stacked-form">
          <Field label="First name">
            <input value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} />
          </Field>
          <Field label="Last name">
            <input value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} />
          </Field>
          <Field label="Email">
            <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </Field>
          <Field label="Password" hint="At least 8 characters.">
            <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength={8} required />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? "Creating..." : "Create account"}
          </Button>
        </form>

        <p className="muted small">
          Already have an account? <Link href="/login">Sign in</Link>. Are you a doctor?{" "}
          <Link href="/activate">Activate your prescriber account</Link>.
        </p>
      </div>
    </div>
  );
}
