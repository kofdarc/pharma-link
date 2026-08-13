"use client";

import { FormEvent, useEffect, useState } from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import type { PublicAvailability } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

function SearchClient() {
  const params = useSearchParams();
  const router = useRouter();
  const [query, setQuery] = useState(params.get("q") || "");
  const [area, setArea] = useState(params.get("area") || "");
  const [results, setResults] = useState<PublicAvailability[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
      .catch(() => setError("Search failed. Please try again."))
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
        <LinkButton href="/login">Pharmacy Login</LinkButton>
      </header>
      <main className="public-main">
        <section className="panel">
          <div className="section-header">
            <div>
              <h1>Public medication availability</h1>
              <p>Results show simplified status only. Exact pharmacy stock numbers are never displayed publicly.</p>
            </div>
          </div>
          <form className="search-bar" onSubmit={submit}>
            <Field label="Medicine">
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Brand, generic, alias..." />
            </Field>
            <Field label="Area">
              <input value={area} onChange={(event) => setArea(event.target.value)} placeholder="Hamra, Achrafieh..." />
            </Field>
            <Button type="submit">Search</Button>
            <Button type="button" variant="secondary" onClick={() => router.push("/search")}>
              Clear
            </Button>
          </form>
          <Notice>Availability information is provided by connected pharmacies and may change. Please confirm with the pharmacy before visiting or using any medication.</Notice>
        </section>

        {loading ? <div className="skeleton-card" /> : null}
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {!query && !loading ? <EmptyState title="Search for a medicine to see availability." /> : null}
        {query && !loading && !error && results.length === 0 ? <EmptyState title="No connected pharmacies currently show this medicine as available." /> : null}
        <section className="result-grid">
          {results.map((result) => (
            <article className="result-card" key={`${result.medicine.id}-${result.pharmacy.id}`}>
              <div className="section-header">
                <div>
                  <h3>{result.medicine.brand_name}</h3>
                  <p className="muted">
                    {[result.medicine.generic_name, result.medicine.strength, result.medicine.form].filter(Boolean).join(" ")}
                  </p>
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
                  Call {result.pharmacy.phone}
                </a>
                {result.pharmacy.whatsapp ? (
                  <a className="button button-secondary" href={`https://wa.me/${result.pharmacy.whatsapp.replace(/\D/g, "")}`}>
                    WhatsApp
                  </a>
                ) : null}
              </div>
              <small className="muted">Last updated {new Date(result.last_updated).toLocaleString()}</small>
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
