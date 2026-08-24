"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { BrandMark } from "@/components/ui/BrandMark";

export default function ResetPasswordPage() {
  const params = useParams<{ uid: string; token: string }>();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiFetch("/auth/password-reset/confirm/", {
        method: "POST",
        body: JSON.stringify({ uid: params.uid, token: params.token, password })
      });
      setDone(true);
    } catch (exception) {
      const apiError = exception as ApiError;
      const details = apiError.details as Record<string, string[]> | undefined;
      const firstField = details ? Object.values(details)[0] : undefined;
      setError(Array.isArray(firstField) ? firstField[0] : apiError.message || "This reset link is invalid or has expired.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <Link href="/" className="brand">
          <BrandMark />
          <span>HealthConnect</span>
        </Link>
        <h1>Set a new password</h1>

        {done ? (
          <>
            <Notice tone="success">Password updated. You can now log in.</Notice>
            <Button type="button" onClick={() => router.push("/login")}>
              Go to login
            </Button>
          </>
        ) : (
          <>
            {error ? <Notice tone="danger">{error}</Notice> : null}
            <form onSubmit={submit} className="stacked-form">
              <Field label="New password" hint="At least 8 characters.">
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
              </Field>
              <Button type="submit" disabled={busy}>
                {busy ? "Saving..." : "Set new password"}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
