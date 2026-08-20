"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { AuditLog, InventoryImport, Medicine, Paginated, Pharmacy, User } from "@/types/api";
import { LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

function totalCount<T>(payload: T[] | Paginated<T>): number {
  return Array.isArray(payload) ? payload.length : payload.count;
}

export default function AdminDashboardPage() {
  const t = useTranslations();
  const [counts, setCounts] = useState({ pharmacies: 0, users: 0, medicines: 0, imports: 0, audit: 0 });
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetch<Pharmacy[] | Paginated<Pharmacy>>("/admin/pharmacies/"),
      apiFetch<User[] | Paginated<User>>("/admin/users/"),
      apiFetch<Medicine[] | Paginated<Medicine>>("/admin/medicines/"),
      apiFetch<InventoryImport[] | Paginated<InventoryImport>>("/admin/imports/"),
      apiFetch<AuditLog[] | Paginated<AuditLog>>("/admin/audit-logs/")
    ])
      .then(([pharmacies, users, medicines, imports, audit]) =>
        setCounts({
          pharmacies: totalCount(pharmacies),
          users: totalCount(users),
          medicines: totalCount(medicines),
          imports: totalCount(imports),
          audit: totalCount(audit)
        })
      )
      .catch(() => setError(t("adminDashboard.loadError")));
  }, [t]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminDashboard.title")}</h1>
          <p>{t("adminDashboard.subtitle")}</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <section className="metrics-grid">
        <div className="metric-card">
          <span>{t("adminDashboard.pharmacies")}</span>
          <strong>{counts.pharmacies}</strong>
        </div>
        <div className="metric-card">
          <span>{t("adminDashboard.users")}</span>
          <strong>{counts.users}</strong>
        </div>
        <div className="metric-card">
          <span>{t("adminDashboard.medicines")}</span>
          <strong>{counts.medicines}</strong>
        </div>
        <div className="metric-card">
          <span>{t("adminDashboard.auditLogs")}</span>
          <strong>{counts.audit}</strong>
        </div>
      </section>
      <div className="actions">
        <LinkButton href="/admin/pharmacies" variant="primary">
          {t("adminDashboard.managePharmacies")}
        </LinkButton>
        <LinkButton href="/admin/medicines">{t("adminDashboard.manageCatalog")}</LinkButton>
        <LinkButton href="/admin/audit-logs">{t("adminDashboard.viewAuditLogs")}</LinkButton>
      </div>
    </>
  );
}

