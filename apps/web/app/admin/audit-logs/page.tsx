"use client";

import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { AuditLog } from "@/types/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminAuditLogsPage() {
  const t = useTranslations();
  const [items, setItems] = useState<AuditLog[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<AuditLog[] | { results: AuditLog[] }>("/admin/audit-logs/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError(t("adminAuditLogs.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminAuditLogs.title")}</h1>
          <p>{t("adminAuditLogs.subtitle")}</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("adminAuditLogs.emptyLogs")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("adminAuditLogs.time")}</th>
              <th>{t("adminAuditLogs.actor")}</th>
              <th>{t("adminAuditLogs.pharmacy")}</th>
              <th>{t("adminAuditLogs.action")}</th>
              <th>{t("adminAuditLogs.summary")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>{item.actor_email}</td>
                <td>{item.pharmacy_name}</td>
                <td>{item.action}</td>
                <td>{item.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

