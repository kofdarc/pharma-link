"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, setToken } from "@/lib/api-client";
import type { User } from "@/types/api";
import { AuthLayout } from "@/components/site/AuthLayout";
import { FormAlert, PasswordField, TextField } from "@/components/site/FormField";
import { SearchVisual } from "@/components/product/Visuals";

interface SignupForm {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  confirm: string;
}

const EMPTY: SignupForm = { first_name: "", last_name: "", email: "", password: "", confirm: "" };

type FieldErrors = Partial<Record<keyof SignupForm | "terms", string>>;

function validate(form: SignupForm, accepted: boolean): FieldErrors {
  const errors: FieldErrors = {};
  if (!form.first_name.trim()) errors.first_name = "Enter your first name.";
  if (!form.last_name.trim()) errors.last_name = "Enter your last name.";
  if (!form.email.trim()) errors.email = "Enter your email address.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) errors.email = "That doesn't look like an email address.";
  if (form.password.length < 8) errors.password = "Use at least 8 characters.";
  if (form.confirm !== form.password) errors.confirm = "Both passwords need to match.";
  if (!accepted) errors.terms = "Please accept the terms to continue.";
  return errors;
}

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState<SignupForm>(EMPTY);
  const [accepted, setAccepted] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key: keyof SignupForm) => (value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    // Clear a field's error as soon as the person starts fixing it.
    setErrors((current) => (current[key] ? { ...current, [key]: undefined } : current));
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate(form, accepted);
    setErrors(found);
    setFormError("");
    if (Object.values(found).some(Boolean)) return;

    setBusy(true);
    try {
      const session = await apiFetch<{ token: string; user: User }>("/auth/register/", {
        method: "POST",
        body: JSON.stringify({
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          email: form.email.trim(),
          password: form.password
        })
      });
      setToken(session.token);
      router.push("/home");
    } catch (exception) {
      // DRF answers with {field: [message]}; surface it against the field when
      // we can, and as a form-level message when we can't.
      const apiError = exception as ApiError;
      const details = apiError.details as Record<string, string[] | string> | undefined;
      const fieldErrors: FieldErrors = {};
      let fallback = "";

      if (details && typeof details === "object") {
        for (const [key, value] of Object.entries(details)) {
          const message = Array.isArray(value) ? value[0] : String(value);
          if (key in EMPTY) fieldErrors[key as keyof SignupForm] = message;
          else fallback = message;
        }
      }

      setErrors(fieldErrors);
      setFormError(Object.keys(fieldErrors).length ? "" : fallback || "We couldn't create the account. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      quote="One search, every connected pharmacy."
      points={[
        "Search medication by brand or generic name",
        "Receive prescriptions digitally from your physician",
        "Have your order sourced and delivered"
      ]}
      visual={<SearchVisual />}
    >
      <h1 className="hc-display">Create your account</h1>
      <p className="hc-body">It takes a minute, and searching stays free.</p>

      <form className="hc-auth-form" onSubmit={submit} noValidate>
        {formError ? <FormAlert>{formError}</FormAlert> : null}

        <div className="hc-auth-row">
          <TextField
            label="First name"
            value={form.first_name}
            onChange={set("first_name")}
            error={errors.first_name}
            required
            autoComplete="given-name"
          />
          <TextField
            label="Last name"
            value={form.last_name}
            onChange={set("last_name")}
            error={errors.last_name}
            required
            autoComplete="family-name"
          />
        </div>

        <TextField
          type="email"
          label="Email address"
          value={form.email}
          onChange={set("email")}
          error={errors.email}
          required
          autoComplete="email"
          placeholder="you@example.com"
          hint="We'll send prescription and order updates here."
        />

        <PasswordField
          label="Password"
          value={form.password}
          onChange={set("password")}
          error={errors.password}
          required
          autoComplete="new-password"
          hint="At least 8 characters."
        />

        <PasswordField
          label="Confirm password"
          value={form.confirm}
          onChange={set("confirm")}
          error={errors.confirm}
          required
          autoComplete="new-password"
        />

        <div>
          <label className="hc-check">
            <input
              type="checkbox"
              checked={accepted}
              aria-invalid={errors.terms ? true : undefined}
              onChange={(event) => {
                setAccepted(event.target.checked);
                setErrors((current) => ({ ...current, terms: undefined }));
              }}
            />
            <span>
              I agree to the HealthConnect Terms and Privacy Policy, and to HealthConnect handling my prescription information to
              fulfil my orders.
            </span>
          </label>
          {errors.terms ? <p className="hc-field-error" style={{ marginTop: 8 }}>{errors.terms}</p> : null}
        </div>

        <button type="submit" className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block" disabled={busy}>
          {busy ? "Creating your account…" : "Create account"}
        </button>
      </form>

      <p className="hc-auth-foot">
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
      <p className="hc-small" style={{ marginTop: 14 }}>
        Physicians <Link href="/activate">activate an account here</Link>. Pharmacies can{" "}
        <Link href="/pharmacy-signup">apply to join</Link>.
      </p>
    </AuthLayout>
  );
}
