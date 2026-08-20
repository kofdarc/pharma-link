"use client";

import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminImportsPage() {
  const t = useTranslations();
  const [items, setItems] = useState<InventoryImport[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<InventoryImport[] | { results: InventoryImport[] }>("/admin/imports/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError(t("adminImports.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminImports.title")}</h1>
          <p>{t("adminImports.subtitle")}</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("adminImports.noImports")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("adminImports.file")}</th>
              <th>{t("adminImports.status")}</th>
              <th>{t("adminImports.totalRows")}</th>
              <th>{t("adminImports.unmatched")}</th>
              <th>{t("adminImports.invalid")}</th>
              <th>{t("adminImports.created")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.original_filename}</td>
                <td>
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                </td>
                <td>{item.total_rows}</td>
                <td>{item.unmatched_rows}</td>
                <td>{item.invalid_rows}</td>
                <td>{item.created_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

