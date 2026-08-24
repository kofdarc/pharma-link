"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { BrandMark } from "@/components/ui/BrandMark";

export default function ForgotPasswordPage() {
  const t = useTranslations();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      // The backend always answers the same way whether or not the account exists, so
      // there's nothing to branch on here beyond "the request went through".
      await apiFetch("/auth/password-reset/", { method: "POST", body: JSON.stringify({ email }) });
    } finally {
      setSent(true);
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
        <div className="section-header">
          <Link href="/" className="brand">
            <BrandMark />
            <span>HealthConnect</span>
          </Link>
          <LanguageSwitcher />
        </div>
        <h1>{t("forgotPassword.title")}</h1>

        {sent ? (
          <Notice tone="success">{t("forgotPassword.sent")}</Notice>
        ) : (
          <>
            <p className="muted">{t("forgotPassword.lead")}</p>
            <form onSubmit={submit} className="stacked-form">
              <Field label={t("common.email")}>
                <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              </Field>
              <Button type="submit" disabled={busy}>
                {busy ? t("forgotPassword.sending") : t("forgotPassword.send")}
              </Button>
            </form>
          </>
        )}

        <p className="muted small">
          {t("forgotPassword.rememberedQuestion")} <Link href="/login">{t("common.signIn")}</Link>.
        </p>
      </div>
    </div>
  );
}
