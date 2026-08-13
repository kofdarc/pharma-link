"use client";

import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { AuditLog, InventoryImport, Medicine, Pharmacy, User } from "@/types/api";
import { LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

export default function AdminDashboardPage() {
  const [counts, setCounts] = useState({ pharmacies: 0, users: 0, medicines: 0, imports: 0, audit: 0 });
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetch<Pharmacy[] | { results: Pharmacy[] }>("/admin/pharmacies/"),
      apiFetch<User[] | { results: User[] }>("/admin/users/"),
      apiFetch<Medicine[] | { results: Medicine[] }>("/admin/medicines/"),
      apiFetch<InventoryImport[] | { results: InventoryImport[] }>("/admin/imports/"),
      apiFetch<AuditLog[] | { results: AuditLog[] }>("/admin/audit-logs/")
    ])
      .then(([pharmacies, users, medicines, imports, audit]) =>
        setCounts({
          pharmacies: asList(pharmacies).length,
          users: asList(users).length,
          medicines: asList(medicines).length,
          imports: asList(imports).length,
          audit: asList(audit).length
        })
      )
      .catch(() => setError("Admin metrics failed to load."));
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Admin</h1>
          <p>Platform-level management for pharmacies, users, catalog records, import issues, and audit logs.</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <section className="metrics-grid">
        <div className="metric-card">
          <span>Pharmacies</span>
          <strong>{counts.pharmacies}</strong>
        </div>
        <div className="metric-card">
          <span>Users</span>
          <strong>{counts.users}</strong>
        </div>
        <div className="metric-card">
          <span>Medicines</span>
          <strong>{counts.medicines}</strong>
        </div>
        <div className="metric-card">
          <span>Audit logs</span>
          <strong>{counts.audit}</strong>
        </div>
      </section>
      <div className="actions">
        <LinkButton href="/admin/pharmacies" variant="primary">
          Manage pharmacies
        </LinkButton>
        <LinkButton href="/admin/medicines">Manage catalog</LinkButton>
        <LinkButton href="/admin/audit-logs">View audit logs</LinkButton>
      </div>
    </>
  );
}

