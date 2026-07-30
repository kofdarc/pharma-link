"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, setToken } from "@/lib/api-client";
import { ROLE_HOME } from "@/lib/constants";
import type { User } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@cedarcare.test");
  const [password, setPassword] = useState("Password123!");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<{ token: string; user: User }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      setToken(response.token);
      router.push(ROLE_HOME[response.user.role] || "/pharmacy/dashboard");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <section className="panel login-card">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>MediSync</span>
        </Link>
        <h1>Login</h1>
        <form className="form-grid" onSubmit={submit}>
          <Field label="Email">
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </Field>
          <Field label="Password">
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </Field>
          <Button type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </form>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <p className="muted small">
          Shopper? <Link href="/register">Create an account</Link>. Doctor?{" "}
          <Link href="/activate">Activate your prescriber account</Link>. Dispensing a QR prescription without an
          account? <Link href="/rx">Go here</Link>.
        </p>
      </section>
    </div>
  );
}

