"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, setToken } from "@/lib/api-client";
import { ROLE_HOME } from "@/lib/constants";
import type { User } from "@/types/api";
import { AuthLayout } from "@/components/site/AuthLayout";
import { FormAlert, PasswordField, TextField } from "@/components/site/FormField";
import { RxCard } from "@/components/product/Visuals";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const expired = searchParams.get("expired") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await apiFetch<{ token: string; user: User }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password })
      });
      setToken(session.token);
      router.push(ROLE_HOME[session.user.role] || "/home");
    } catch {
      setError("That email and password don't match an account. Check them and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      quote="Your prescriptions, orders and refills — in one place."
      points={[
        "See prescriptions your physician issued you",
        "Track an order from the pharmacy to your door",
        "Keep repeat medication on a schedule"
      ]}
      visual={<RxCard />}
    >
      <h1 className="hc-display">Welcome back</h1>
      <p className="hc-body">Sign in to pick up where you left off.</p>

      <form className="hc-auth-form" onSubmit={submit} noValidate>
        {expired ? <FormAlert tone="info">Your session timed out. Sign in again to continue.</FormAlert> : null}
        {error ? <FormAlert>{error}</FormAlert> : null}

        <TextField
          type="email"
          label="Email address"
          value={email}
          onChange={setEmail}
          required
          autoComplete="email"
          placeholder="you@example.com"
        />
        <PasswordField label="Password" value={password} onChange={setPassword} required autoComplete="current-password" />

        <div className="hc-auth-meta">
          <Link href="/forgot-password" className="hc-textlink">
            Forgot your password?
          </Link>
        </div>

        <button type="submit" className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="hc-auth-foot">
        New to HealthConnect? <Link href="/register">Create an account</Link>
      </p>
      <p className="hc-small" style={{ marginTop: 14 }}>
        Physicians can <Link href="/activate">activate an account</Link>, and pharmacies can{" "}
        <Link href="/pharmacy-signup">apply to join</Link>. Dispensing a prescription? <Link href="/rx">Start here</Link>.
      </p>
    </AuthLayout>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="hc" />}>
      <LoginForm />
    </Suspense>
  );
}
