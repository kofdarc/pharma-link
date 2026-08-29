"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ImportsPage() {
  const t = useTranslations();
  const [items, setItems] = useState<InventoryImport[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryImport[] | { results: InventoryImport[] }>("/pharmacy/imports/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError(t("pharmacyImports.loadError")));
  }

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<InventoryImport>("/pharmacy/imports/upload/", { method: "POST", body: form });
      setMessage(t("pharmacyImports.parsedMessage"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("pharmacyImports.uploadFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyImports.title")}</h1>
          <p>{t("pharmacyImports.subtitle")}</p>
        </div>
      </div>
      <form className="panel toolbar" onSubmit={upload}>
        <Field label={t("pharmacyImports.inventoryFile")} hint={t("pharmacyImports.inventoryFileHint")}>
          <input type="file" name="file" accept=".csv,.xlsx" required />
        </Field>
        <Button type="submit">{t("pharmacyImports.uploadPreview")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("pharmacyImports.noImports")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacyImports.file")}</th>
              <th>{t("pharmacyImports.status")}</th>
              <th>{t("pharmacyImports.rows")}</th>
              <th>{t("pharmacyImports.matched")}</th>
              <th>{t("pharmacyImports.created")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link href={`/pharmacy/imports/${item.id}`}>
                    <strong>{item.original_filename}</strong>
                  </Link>
                </td>
                <td>
                  <Badge status tone={statusTone(item.status)}>{item.status}</Badge>
                </td>
                <td>{item.total_rows}</td>
                <td>{item.matched_rows}</td>
                <td>{item.created_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}
