"use client";

import { FormEvent, useEffect, useState } from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, Pharmacy, PublicAvailability } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ProductThumb } from "@/components/ui/ProductThumb";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";

function SearchClient() {
  const params = useSearchParams();
  const router = useRouter();
  const t = useTranslations();
  const [query, setQuery] = useState(params.get("q") || "");
  const [area, setArea] = useState(params.get("area") || "");
  const [areaOptions, setAreaOptions] = useState<string[]>([]);
  const [results, setResults] = useState<PublicAvailability[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Paginated<Pharmacy> | Pharmacy[]>("/public/pharmacies/")
      .then((payload) => {
        const areas = Array.from(new Set(asList(payload).map((pharmacy) => pharmacy.area).filter(Boolean)));
        areas.sort((a, b) => a.localeCompare(b));
        setAreaOptions(areas);
      })
      .catch(() => setAreaOptions([]));
  }, []);

  useEffect(() => {
    const q = params.get("q") || "";
    const selectedArea = params.get("area") || "";
    setQuery(q);
    setArea(selectedArea);
    if (!q) return;
    setLoading(true);
    setError("");
    apiFetch<PublicAvailability[]>(`/public/search/?q=${encodeURIComponent(q)}&area=${encodeURIComponent(selectedArea)}`)
      .then(setResults)
      .catch(() => setError(t("search.searchFailed")))
      .finally(() => setLoading(false));
  }, [params]);

  function submit(event: FormEvent) {
    event.preventDefault();
    router.push(`/search?q=${encodeURIComponent(query)}&area=${encodeURIComponent(area)}`);
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
          <LinkButton href="/login">{t("nav.pharmacyLogin")}</LinkButton>
        </div>
      </header>
      <main className="public-main">
        <section className="panel">
          <div className="section-header">
            <div>
              <h1>{t("search.title")}</h1>
              <p>{t("search.subtitle")}</p>
            </div>
          </div>
          <form className="search-bar" onSubmit={submit}>
            <Field label={t("search.medicine")}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("search.medicinePlaceholder")} />
            </Field>
            <Field label={t("search.area")}>
              <select value={area} onChange={(event) => setArea(event.target.value)}>
                <option value="">{t("search.allAreas")}</option>
                {areaOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </Field>
            <Button type="submit">{t("common.search")}</Button>
            <Button type="button" variant="secondary" onClick={() => router.push("/search")}>
              {t("search.clear")}
            </Button>
          </form>
          <Notice>{t("search.disclaimer")}</Notice>
        </section>

        {loading ? <div className="skeleton-card" /> : null}
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {!query && !loading ? <EmptyState title={t("search.promptSearch")} /> : null}
        {query && !loading && !error && results.length === 0 ? <EmptyState title={t("search.noResults")} /> : null}
        <section className="result-grid">
          {results.map((result) => (
            <article className="result-card" key={`${result.medicine.id}-${result.pharmacy.id}`}>
              <div className="section-header">
                <div className="actions">
                  <ProductThumb src={result.medicine.image} alt={result.medicine.brand_name} />
                  <div>
                    <h3>{result.medicine.brand_name}</h3>
                    <p className="muted">
                      {[result.medicine.generic_name, result.medicine.strength, result.medicine.form].filter(Boolean).join(" ")}
                    </p>
                  </div>
                </div>
                <Badge tone={statusTone(result.availability_status)}>{result.availability_status}</Badge>
              </div>
              <div>
                <strong>{result.pharmacy.name}</strong>
                <p className="muted">
                  {result.pharmacy.area}, {result.pharmacy.city}
                </p>
                <p>{result.pharmacy.address}</p>
              </div>
              <div className="actions">
                <a className="button button-secondary" href={`tel:${result.pharmacy.phone}`}>
                  {t("search.call", { phone: result.pharmacy.phone })}
                </a>
                {result.pharmacy.whatsapp ? (
                  <a className="button button-secondary" href={`https://wa.me/${result.pharmacy.whatsapp.replace(/\D/g, "")}`}>
                    {t("search.whatsapp")}
                  </a>
                ) : null}
              </div>
              <small className="muted">{t("search.lastUpdated", { when: new Date(result.last_updated).toLocaleString() })}</small>
            </article>
          ))}
        </section>
      </main>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="center-screen"><div className="skeleton-card" /></div>}>
      <SearchClient />
    </Suspense>
  );
}
