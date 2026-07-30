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

      <section className="public-main">
        <h2>Who is this for?</h2>
        <div className="role-grid">
          <article className="role-card">
            <h3>Pharmacies</h3>
            <p>
              Stock, batches and expiry risk, invoicing, client records, analytics — and a connector that keeps your
              existing software in sync instead of replacing it.
            </p>
            <LinkButton href="/login" variant="primary">
              Pharmacy login
            </LinkButton>
          </article>

          <article className="role-card">
            <h3>Doctors</h3>
            <p>
              Your details are already on file from the Order of Physicians. Activate in a minute and issue
              prescriptions as secure QR codes.
            </p>
            <LinkButton href="/activate" variant="primary">
              Activate your account
            </LinkButton>
          </article>

          <article className="role-card">
            <h3>Any pharmacy, no account</h3>
            <p>
              Holding a patient&apos;s prescription QR? Scan it, view the items, and dispense in full or in part. No
              registration, no login.
            </p>
            <LinkButton href="/rx" variant="primary">
              Dispense a prescription
            </LinkButton>
          </article>

          <article className="role-card">
            <h3>Patients</h3>
            <p>
              Find what you need across every connected pharmacy at once, order it, and schedule repeat refills for
              chronic medication.
            </p>
            <LinkButton href="/register" variant="primary">
              Create an account
            </LinkButton>
          </article>
        </div>
      </section>
    </div>
  );
}

