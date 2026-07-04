"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { Sale } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function SalesPage() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Sale[] | { results: Sale[] }>("/pharmacy/sales/")
      .then((payload) => setSales(asList(payload)))
      .catch(() => setError("Sales failed to load."));
  }, []);

  const total = sales.reduce((sum, sale) => sum + Number(sale.total), 0);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Sales and invoices</h1>
          <p>Completed sales deduct inventory and create invoice records.</p>
        </div>
        <LinkButton href="/pharmacy/sales/new" variant="primary">
          Create sale
        </LinkButton>
      </div>
      <section className="metrics-grid">
        <div className="metric-card">
          <span>Invoices</span>
          <strong>{sales.length}</strong>
        </div>
        <div className="metric-card">
          <span>Total revenue</span>
          <strong>${total.toFixed(2)}</strong>
        </div>
      </section>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {sales.length === 0 ? <EmptyState title="No sales recorded yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Invoice</th>
              <th>Date</th>
              <th>Staff</th>
              <th>Status</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {sales.map((sale) => (
              <tr key={sale.id}>
                <td>
                  <Link href={`/pharmacy/invoices/${sale.id}`}>
                    <strong>{sale.invoice_number}</strong>
                  </Link>
                </td>
                <td>{new Date(sale.sale_datetime).toLocaleString()}</td>
                <td>{sale.staff_email}</td>
                <td>
                  <Badge tone={statusTone(sale.status)}>{sale.status}</Badge>
                </td>
                <td>${sale.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

