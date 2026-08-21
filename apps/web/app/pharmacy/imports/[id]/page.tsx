"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ImportDetailPage() {
  const t = useTranslations();
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<InventoryImport | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryImport>(`/pharmacy/imports/${id}/`).then(setItem).catch(() => setError(t("pharmacyImportDetail.notFound")));
  }

  useEffect(load, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function confirm() {
    setError("");
    setMessage("");
    try {
      const updated = await apiFetch<InventoryImport>(`/pharmacy/imports/${id}/confirm/`, { method: "POST" });
      setItem(updated);
      setMessage(t("pharmacyImportDetail.confirmedMessage"));
    } catch {
      setError(t("pharmacyImportDetail.confirmFailed"));
    }
  }

  if (!item) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{item.original_filename}</h1>
          <p>
            {t("pharmacyImportDetail.summary", {
              created: item.created_count,
              skipped: item.skipped_count,
              invalid: item.invalid_rows,
              unmatched: item.unmatched_rows
            })}
          </p>
        </div>
        <div className="actions">
          <Badge tone={statusTone(item.status)}>{item.status}</Badge>
          {item.status === "PARSED" ? <Button onClick={confirm}>{t("pharmacyImportDetail.confirmImport")}</Button> : null}
        </div>
      </div>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacyImportDetail.row")}</th>
              <th>{t("pharmacyImportDetail.medicine")}</th>
              <th>{t("pharmacyImportDetail.match")}</th>
              <th>{t("pharmacyImportDetail.quantity")}</th>
              <th>{t("pharmacyImportDetail.status")}</th>
              <th>{t("pharmacyImportDetail.error")}</th>
            </tr>
          </thead>
          <tbody>
            {(item.rows || []).map((row) => (
              <tr key={row.id}>
                <td>{row.row_number}</td>
                <td>{row.raw_medicine_name}</td>
                <td>{row.matched_medicine_detail?.display_name || t("pharmacyImportDetail.manualMatchRequired")}</td>
                <td>{row.quantity || ""}</td>
                <td>
                  <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                </td>
                <td>{row.error_message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </section>
  );
}

