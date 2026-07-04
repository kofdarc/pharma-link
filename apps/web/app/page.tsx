"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button, LinkButton } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function HomePage() {
  const router = useRouter();
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
          <span>MediSync</span>
        </Link>
        <div className="actions">
          <LinkButton href="/search">Public Search</LinkButton>
          <LinkButton href="/login" variant="primary">
            Pharmacy Login
          </LinkButton>
        </div>
      </header>
      <main className="public-main intro-grid">
        <section>
          <h1 className="page-title">Find connected pharmacies that may have your medicine.</h1>
          <p className="lead">
            MediSync helps Lebanese pharmacies manage stock, batches, expiry risk, sales, prescriptions, and public availability from one operational workspace.
          </p>
          <Notice>
            Availability information is provided by connected pharmacies and may change. Please confirm with the pharmacy before visiting or using any medication.
          </Notice>
        </section>
        <section className="panel">
          <h2>Medication search</h2>
          <p className="muted">Search by brand, generic name, alias, or partial spelling.</p>
          <form className="search-bar" onSubmit={submit}>
            <Field label="Medicine">
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Panadol, paracetamol..." />
            </Field>
            <Button type="submit">Search</Button>
          </form>
        </section>
      </main>
    </div>
  );
}

