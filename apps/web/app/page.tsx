"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "@/lib/i18n/context";
import { Button, LinkButton } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";

export default function HomePage() {
  const router = useRouter();
  const t = useTranslations();
  const [query, setQuery] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    router.push(`/search?q=${encodeURIComponent(query)}`);
  }

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>PharmaLink</span>
        </Link>
        <div className="actions">
          <LanguageSwitcher />
          <LinkButton href="/search">{t("nav.publicSearch")}</LinkButton>
          <LinkButton href="/login" variant="primary">
            {t("nav.pharmacyLogin")}
          </LinkButton>
        </div>
      </header>
      <main className="public-main intro-grid">
        <section>
          <h1 className="page-title">{t("home.title")}</h1>
          <p className="lead">{t("home.lead")}</p>
          <Notice>{t("home.disclaimer")}</Notice>
        </section>
        <section className="panel">
          <h2>{t("home.searchTitle")}</h2>
          <p className="muted">{t("home.searchHint")}</p>
          <form className="search-bar" onSubmit={submit}>
            <Field label={t("common.search")}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("home.searchPlaceholder")} />
            </Field>
            <Button type="submit">{t("common.search")}</Button>
          </form>
        </section>
      </main>

      <section className="public-main">
        <h2>{t("home.whoTitle")}</h2>
        <div className="role-grid">
          <article className="role-card">
            <h3>{t("home.pharmacies.title")}</h3>
            <p>{t("home.pharmacies.body")}</p>
            <LinkButton href="/login" variant="primary">
              {t("home.pharmacies.cta")}
            </LinkButton>
            <p className="muted small">
              {t("home.pharmacies.newPharmacy")} <Link href="/pharmacy-signup">{t("home.pharmacies.apply")}</Link>.
            </p>
          </article>

          <article className="role-card">
            <h3>{t("home.doctors.title")}</h3>
            <p>{t("home.doctors.body")}</p>
            <LinkButton href="/activate" variant="primary">
              {t("home.doctors.cta")}
            </LinkButton>
          </article>

          <article className="role-card">
            <h3>{t("home.anyPharmacy.title")}</h3>
            <p>{t("home.anyPharmacy.body")}</p>
            <LinkButton href="/rx" variant="primary">
              {t("home.anyPharmacy.cta")}
            </LinkButton>
          </article>

          <article className="role-card">
            <h3>{t("home.patients.title")}</h3>
            <p>{t("home.patients.body")}</p>
            <LinkButton href="/register" variant="primary">
              {t("home.patients.cta")}
            </LinkButton>
          </article>
        </div>
      </section>
    </div>
  );
}

