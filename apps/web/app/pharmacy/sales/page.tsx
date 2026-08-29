"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Sale } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function SalesPage() {
  const t = useTranslations();
  const [sales, setSales] = useState<Sale[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Sale[] | { results: Sale[] }>("/pharmacy/sales/")
      .then((payload) => setSales(asList(payload)))
      .catch(() => setError(t("pharmacySales.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const total = sales.reduce((sum, sale) => sum + Number(sale.total), 0);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacySales.title")}</h1>
          <p>{t("pharmacySales.subtitle")}</p>
        </div>
        <LinkButton href="/pharmacy/sales/new" variant="primary">
          {t("pharmacySales.createSale")}
        </LinkButton>
      </div>
      <section className="metrics-grid">
        <div className="metric-card">
          <span>{t("pharmacySales.invoices")}</span>
          <strong>{sales.length}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacySales.totalRevenue")}</span>
          <strong>${total.toFixed(2)}</strong>
        </div>
      </section>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {sales.length === 0 ? <EmptyState title={t("pharmacySales.noSalesYet")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacySales.invoice")}</th>
              <th>{t("pharmacySales.date")}</th>
              <th>{t("pharmacySales.staff")}</th>
              <th>{t("pharmacySales.status")}</th>
              <th>{t("pharmacySales.total")}</th>
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
                  <Badge status tone={statusTone(sale.status)}>{sale.status}</Badge>
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
