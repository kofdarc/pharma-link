"use client";

import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { InventoryImport } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminImportsPage() {
  const [items, setItems] = useState<InventoryImport[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<InventoryImport[] | { results: InventoryImport[] }>("/admin/imports/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError("Imports failed to load."));
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Import issues</h1>
          <p>Review import history and unmatched rows across pharmacies.</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="No imports yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Total rows</th>
              <th>Unmatched</th>
              <th>Invalid</th>
              <th>Created</th>
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

