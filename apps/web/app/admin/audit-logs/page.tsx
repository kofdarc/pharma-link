"use client";

import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { AuditLog } from "@/types/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminAuditLogsPage() {
  const [items, setItems] = useState<AuditLog[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<AuditLog[] | { results: AuditLog[] }>("/admin/audit-logs/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError("Audit logs failed to load."));
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Audit logs</h1>
          <p>Append-only records for sensitive actions.</p>
        </div>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="Empty logs." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Pharmacy</th>
              <th>Action</th>
              <th>Summary</th>
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

