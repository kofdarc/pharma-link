"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, setToken } from "@/lib/api-client";
import { ROLE_HOME } from "@/lib/constants";
import { useTranslations } from "@/lib/i18n/context";
import type { User } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { BrandMark } from "@/components/ui/BrandMark";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations();
  const expired = searchParams.get("expired") === "1";
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
      setError(t("login.error"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <section className="panel login-card">
        <div className="section-header">
          <Link href="/" className="brand">
            <BrandMark />
            <span>PharmaLink</span>
          </Link>
          <LanguageSwitcher />
        </div>
        <h1>{t("login.title")}</h1>
        {expired ? <Notice tone="info">{t("login.expired")}</Notice> : null}
        <form className="form-grid" onSubmit={submit}>
          <Field label={t("common.email")}>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </Field>
          <Field label={t("common.password")}>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </Field>
          <Button type="submit" disabled={loading}>
            {loading ? t("common.signingIn") : t("common.signIn")}
          </Button>
        </form>
        <p className="muted small">
          <Link href="/forgot-password">{t("login.forgotPassword")}</Link>
        </p>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <p className="muted small">
          {t("login.shopperQuestion")} <Link href="/register">{t("login.createAccount")}</Link>. {t("login.doctorQuestion")}{" "}
          <Link href="/activate">{t("login.activateAccount")}</Link>. {t("login.dispensingQuestion")}{" "}
          <Link href="/rx">{t("login.goHere")}</Link>.
        </p>
      </section>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="center-screen" />}>
      <LoginForm />
    </Suspense>
  );
}

