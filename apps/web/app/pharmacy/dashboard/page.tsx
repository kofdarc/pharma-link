"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

interface DashboardData {
  metrics: {
    inventory_batches: number;
    low_stock_count: number;
    expiring_soon_count: number;
    sales_today: number;
  };
  low_stock: { id: string; medicine: string; current_quantity: number; threshold: number }[];
  expiring_soon: { id: string; medicine: string; expiry_date: string; current_quantity: number }[];
  recent_sales: { id: string; invoice_number: string; total: string; sale_datetime: string }[];
  recent_audit: { id: string; action: string; summary: string; created_at: string }[];
}

export default function PharmacyDashboardPage() {
  const t = useTranslations();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DashboardData>("/pharmacy/dashboard/")
      .then(setData)
      .catch(() => setError(t("pharmacyDashboard.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <Notice tone="danger">{error}</Notice>;
  if (!data) return <div className="skeleton-card" />;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyDashboard.title")}</h1>
          <p>{t("pharmacyDashboard.subtitle")}</p>
        </div>
        <div className="actions">
          <LinkButton href="/pharmacy/inventory/new" variant="primary">
            {t("pharmacyDashboard.addStock")}
          </LinkButton>
          <LinkButton href="/pharmacy/sales/new">{t("pharmacyDashboard.recordSale")}</LinkButton>
        </div>
      </div>
      <section className="metrics-grid">
        <div className="metric-card">
          <span>{t("pharmacyDashboard.inventoryBatches")}</span>
          <strong>{data.metrics.inventory_batches}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyDashboard.lowStock")}</span>
          <strong>{data.metrics.low_stock_count}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyDashboard.expiringSoon")}</span>
          <strong>{data.metrics.expiring_soon_count}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyDashboard.salesToday")}</span>
          <strong>{data.metrics.sales_today}</strong>
        </div>
      </section>
      <section className="panel panel-highlight">
        <div className="section-header">
          <div>
            <h2>{t("pharmacyDashboard.connectExistingSystem")}</h2>
            <p className="muted small">{t("pharmacyDashboard.connectExistingSystemHint")}</p>
          </div>
          <LinkButton href="/pharmacy/connect" variant="primary">
            {t("pharmacyDashboard.openConnectionSetup")}
          </LinkButton>
        </div>
      </section>
      {data.metrics.inventory_batches === 0 ? <EmptyState title={t("pharmacyDashboard.noInventoryYet")} /> : null}
      <section className="split-grid">
        <div className="panel">
          <h2>{t("pharmacyDashboard.lowStockAlerts")}</h2>
          <Table>
            <table>
              <thead>
                <tr>
                  <th>{t("pharmacyDashboard.medicine")}</th>
                  <th>{t("pharmacyDashboard.status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.low_stock.map((item) => (
                  <tr key={item.id}>
                    <td>{item.medicine}</td>
                    <td>
                      <Badge tone="warning">{`${item.current_quantity} <= ${item.threshold}`}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        </div>
        <div className="panel">
          <h2>{t("pharmacyDashboard.expiringSoon")}</h2>
          <Table>
            <table>
              <thead>
                <tr>
                  <th>{t("pharmacyDashboard.medicine")}</th>
                  <th>{t("pharmacyDashboard.expiry")}</th>
                </tr>
              </thead>
              <tbody>
                {data.expiring_soon.map((item) => (
                  <tr key={item.id}>
                    <td>{item.medicine}</td>
                    <td>
                      <Badge tone="warning">{new Date(item.expiry_date).toLocaleDateString()}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        </div>
      </section>
      <section className="split-grid" style={{ marginTop: 16 }}>
        <div className="panel">
          <h2>{t("pharmacyDashboard.recentSales")}</h2>
          {data.recent_sales.length === 0 ? <EmptyState title={t("pharmacyDashboard.noSalesYet")} /> : null}
          {data.recent_sales.map((sale) => (
            <p key={sale.id}>
              <strong>{sale.invoice_number}</strong> <span className="muted">${sale.total}</span>
            </p>
          ))}
        </div>
        <div className="panel">
          <h2>{t("pharmacyDashboard.recentActivity")}</h2>
          {data.recent_audit.map((log) => (
            <p key={log.id}>
              <strong>{log.action}</strong> <span className="muted">{log.summary}</span>
            </p>
          ))}
        </div>
      </section>
    </>
  );
}
