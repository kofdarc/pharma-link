"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, setToken } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { User } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { BrandMark } from "@/components/ui/BrandMark";

/** Shopper self-signup. Only the CUSTOMER role can be self-assigned. */
export default function RegisterPage() {
  const router = useRouter();
  const t = useTranslations();
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
      setError(Array.isArray(firstField) ? firstField[0] : apiError.message || t("register.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <div className="section-header">
          <Link href="/" className="brand">
            <BrandMark />
            <span>PharmaLink</span>
          </Link>
          <LanguageSwitcher />
        </div>
        <h1>{t("register.title")}</h1>
        <p className="muted">{t("register.lead")}</p>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <form onSubmit={submit} className="stacked-form">
          <Field label={t("register.firstName")}>
            <input value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} />
          </Field>
          <Field label={t("register.lastName")}>
            <input value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} />
          </Field>
          <Field label={t("common.email")}>
            <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </Field>
          <Field label={t("common.password")} hint={t("register.passwordHint")}>
            <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength={8} required />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? t("register.creating") : t("register.createAccount")}
          </Button>
        </form>

        <p className="muted small">
          {t("register.haveAccountQuestion")} <Link href="/login">{t("register.signIn")}</Link>. {t("register.doctorQuestion")}{" "}
          <Link href="/activate">{t("register.activateAccount")}</Link>.
        </p>
      </div>
    </div>
  );
}
