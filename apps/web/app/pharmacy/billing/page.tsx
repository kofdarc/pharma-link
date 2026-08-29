"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, PharmacySubscription, PlatformServiceFee } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function feeTone(status: PlatformServiceFee["status"]) {
  if (status === "PAID") return "success" as const;
  if (status === "WAIVED") return "neutral" as const;
  return "warning" as const;
}

export default function PharmacyBillingPage() {
  const t = useTranslations();
  const [subscription, setSubscription] = useState<PharmacySubscription | null>(null);
  const [fees, setFees] = useState<PlatformServiceFee[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [subscriptionResult, feeData] = await Promise.all([
        apiFetch<PharmacySubscription>("/pharmacy/subscription/").catch(() => null),
        apiFetch<Paginated<PlatformServiceFee> | PlatformServiceFee[]>("/pharmacy/service-fees/")
      ]);
      setSubscription(subscriptionResult);
      setFees(asList(feeData));
    } catch {
      setError(t("pharmacyBilling.loadError"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <div className="skeleton-card" />;

  const pendingTotal = fees.filter((fee) => fee.status === "PENDING").reduce((sum, fee) => sum + Number(fee.amount), 0);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyBilling.title")}</h1>
          <p className="muted">{t("pharmacyBilling.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <section className="panel">
        <h3>{t("pharmacyBilling.subscription")}</h3>
        {subscription ? (
          <dl className="detail-grid">
            <div>
              <dt>{t("pharmacyBilling.plan")}</dt>
              <dd>{subscription.plan_detail.name}</dd>
            </div>
            <div>
              <dt>{t("pharmacyBilling.monthlyFee")}</dt>
              <dd>${subscription.plan_detail.monthly_fee}</dd>
            </div>
            <div>
              <dt>{t("pharmacyBilling.perRequestFee")}</dt>
              <dd>${subscription.plan_detail.service_fee_per_request}</dd>
            </div>
            <div>
              <dt>{t("pharmacyBilling.status")}</dt>
              <dd>
                <Badge status tone={subscription.status === "ACTIVE" ? "success" : subscription.status === "PAST_DUE" ? "warning" : "neutral"}>
                  {subscription.status}
                </Badge>
              </dd>
            </div>
          </dl>
        ) : (
          <EmptyState title={t("pharmacyBilling.noSubscription")} detail={t("pharmacyBilling.noSubscriptionHint")} />
        )}
      </section>

      <section className="panel">
        <div className="section-header">
          <h3>{t("pharmacyBilling.serviceFees")}</h3>
          <span className="muted small">{t("pharmacyBilling.pendingAmount", { amount: `$${pendingTotal.toFixed(2)}` })}</span>
        </div>
        <p className="muted small">{t("pharmacyBilling.feesChargedHint")}</p>
        {fees.length === 0 ? (
          <EmptyState title={t("pharmacyBilling.noFeesYet")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyBilling.order")}</th>
                  <th>{t("pharmacyBilling.amount")}</th>
                  <th>{t("pharmacyBilling.status")}</th>
                  <th>{t("pharmacyBilling.charged")}</th>
                </tr>
              </thead>
              <tbody>
                {fees.map((fee) => (
                  <tr key={fee.id}>
                    <td>{fee.order_reference}</td>
                    <td>${fee.amount}</td>
                    <td>
                      <Badge status tone={feeTone(fee.status)}>{fee.status}</Badge>
                    </td>
                    <td className="muted small">{new Date(fee.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>
    </>
  );
}
