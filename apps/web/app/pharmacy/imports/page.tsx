"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ImportsPage() {
  const [items, setItems] = useState<InventoryImport[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryImport[] | { results: InventoryImport[] }>("/pharmacy/imports/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError("Imports failed to load."));
  }

  useEffect(load, []);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<InventoryImport>("/pharmacy/imports/upload/", { method: "POST", body: form });
      setMessage("Import parsed. Review the preview before confirming.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Upload failed. Use CSV or XLSX with Medicine name and Quantity columns.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Imports</h1>
          <p>Upload CSV or XLSX stock files, then confirm matched rows before inventory is created.</p>
        </div>
      </div>
      <form className="panel toolbar" onSubmit={upload}>
        <Field label="Inventory file" hint="Required columns: Medicine name, Quantity. Selling price is required for MVP imports.">
          <input type="file" name="file" accept=".csv,.xlsx" required />
        </Field>
        <Button type="submit">Upload preview</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="No imports yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Rows</th>
              <th>Matched</th>
              <th>Created</th>
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
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
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

