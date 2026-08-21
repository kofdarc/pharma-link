"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { BrandMark } from "@/components/ui/BrandMark";

/** Public: how a prospective pharmacy asks to join, since only a platform admin can create a Pharmacy directly. */
export default function PharmacySignupPage() {
  const [form, setForm] = useState({
    pharmacy_name: "",
    owner_name: "",
    email: "",
    phone: "",
    city: "",
    area: "",
    license_number: "",
    message: ""
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiFetch("/public/pharmacy-applications/", { method: "POST", body: JSON.stringify(form) });
      setSubmitted(true);
    } catch (exception) {
      const apiError = exception as ApiError;
      const details = apiError.details as Record<string, string[]> | undefined;
      const firstField = details ? Object.values(details)[0] : undefined;
      setError(Array.isArray(firstField) ? firstField[0] : apiError.message || "Could not submit your application.");
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <div className="center-screen">
        <div className="auth-card">
          <Link href="/" className="brand">
            <BrandMark />
            <span>PharmaLink</span>
          </Link>
          <h1>Application received</h1>
          <Notice tone="success">
            Thanks — we&apos;ll review your application and email {form.email} with next steps.
          </Notice>
        </div>
      </div>
    );
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <Link href="/" className="brand">
          <BrandMark />
          <span>PharmaLink</span>
        </Link>
        <h1>Bring your pharmacy onto PharmaLink</h1>
        <p className="muted">Tell us about your pharmacy and we&apos;ll set up your account. You keep your own software.</p>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <form onSubmit={submit} className="stacked-form">
          <Field label="Pharmacy name">
            <input value={form.pharmacy_name} onChange={(event) => setForm({ ...form, pharmacy_name: event.target.value })} required />
          </Field>
          <Field label="Owner name">
            <input value={form.owner_name} onChange={(event) => setForm({ ...form, owner_name: event.target.value })} required />
          </Field>
          <Field label="Email">
            <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </Field>
          <Field label="Phone">
            <input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} required />
          </Field>
          <Field label="City">
            <input value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} />
          </Field>
          <Field label="Area">
            <input value={form.area} onChange={(event) => setForm({ ...form, area: event.target.value })} />
          </Field>
          <Field label="License number" hint="If you have one already.">
            <input value={form.license_number} onChange={(event) => setForm({ ...form, license_number: event.target.value })} />
          </Field>
          <Field label="Anything else?">
            <textarea value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} rows={3} />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? "Submitting..." : "Submit application"}
          </Button>
        </form>

        <p className="muted small">
          Already have an account? <Link href="/login">Sign in</Link>.
        </p>
      </div>
    </div>
  );
}
