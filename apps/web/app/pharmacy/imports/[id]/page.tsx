"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ImportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<InventoryImport | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryImport>(`/pharmacy/imports/${id}/`).then(setItem).catch(() => setError("Import not found."));
  }

  useEffect(load, [id]);

  async function confirm() {
    setError("");
    setMessage("");
    try {
      const updated = await apiFetch<InventoryImport>(`/pharmacy/imports/${id}/confirm/`, { method: "POST" });
      setItem(updated);
      setMessage("Import confirmed. Matched rows created inventory batches and stock movements.");
    } catch {
      setError("Confirm failed. Only parsed imports can be confirmed.");
    }
  }

  if (!item) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{item.original_filename}</h1>
          <p>
            {item.created_count} created, {item.skipped_count} skipped, {item.invalid_rows} invalid, {item.unmatched_rows} unmatched.
          </p>
        </div>
        <div className="actions">
          <Badge tone={statusTone(item.status)}>{item.status}</Badge>
          {item.status === "PARSED" ? <Button onClick={confirm}>Confirm import</Button> : null}
        </div>
      </div>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Row</th>
              <th>Medicine</th>
              <th>Match</th>
              <th>Quantity</th>
              <th>Status</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {(item.rows || []).map((row) => (
              <tr key={row.id}>
                <td>{row.row_number}</td>
                <td>{row.raw_medicine_name}</td>
                <td>{row.matched_medicine_detail?.display_name || "Manual match required"}</td>
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

