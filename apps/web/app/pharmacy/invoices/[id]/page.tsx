"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { Sale } from "@/types/api";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function InvoiceDetailPage() {
  const t = useTranslations();
  const { id } = useParams<{ id: string }>();
  const [sale, setSale] = useState<Sale | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Sale>(`/pharmacy/invoices/${id}/`).then(setSale).catch(() => setError(t("pharmacyInvoiceDetail.notFound")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!sale) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{sale.invoice_number}</h1>
          <p>{t("pharmacyInvoiceDetail.byStaff", { when: new Date(sale.sale_datetime).toLocaleString(), staff: sale.staff_email })}</p>
        </div>
        <Badge status tone={statusTone(sale.status)}>{sale.status}</Badge>
      </div>
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacyInvoiceDetail.medicine")}</th>
              <th>{t("pharmacyInvoiceDetail.batch")}</th>
              <th>{t("pharmacyInvoiceDetail.quantity")}</th>
              <th>{t("pharmacyInvoiceDetail.unitPrice")}</th>
              <th>{t("pharmacyInvoiceDetail.discount")}</th>
              <th>{t("pharmacyInvoiceDetail.total")}</th>
            </tr>
          </thead>
          <tbody>
            {sale.items.map((item) => (
              <tr key={item.id}>
                <td>{item.medicine_detail.display_name}</td>
                <td>{item.batch_number}</td>
                <td>{item.quantity}</td>
                <td>${item.unit_price}</td>
                <td>${item.discount}</td>
                <td>${item.line_total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
      <section className="metrics-grid" style={{ marginTop: 16 }}>
        <div className="metric-card">
          <span>{t("pharmacyInvoiceDetail.subtotal")}</span>
          <strong>${sale.subtotal}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyInvoiceDetail.discount")}</span>
          <strong>${sale.discount_total}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyInvoiceDetail.total")}</span>
          <strong>${sale.total}</strong>
        </div>
      </section>
    </section>
  );
}
