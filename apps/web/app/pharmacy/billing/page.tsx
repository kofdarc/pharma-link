"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
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
      setError("Could not load your billing information.");
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
          <h1>Billing</h1>
          <p className="muted">Your subscription plan and the per-request service fees it charges.</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <section className="panel">
        <h3>Subscription</h3>
        {subscription ? (
          <dl className="detail-grid">
            <div>
              <dt>Plan</dt>
              <dd>{subscription.plan_detail.name}</dd>
            </div>
            <div>
              <dt>Monthly fee</dt>
              <dd>${subscription.plan_detail.monthly_fee}</dd>
            </div>
            <div>
              <dt>Per-request fee</dt>
              <dd>${subscription.plan_detail.service_fee_per_request}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <Badge tone={subscription.status === "ACTIVE" ? "success" : subscription.status === "PAST_DUE" ? "warning" : "neutral"}>
                  {subscription.status}
                </Badge>
              </dd>
            </div>
          </dl>
        ) : (
          <EmptyState title="No subscription on file." detail="Contact PharmaLink to get set up on a plan." />
        )}
      </section>

      <section className="panel">
        <div className="section-header">
          <h3>Service fees</h3>
          <span className="muted small">${pendingTotal.toFixed(2)} pending</span>
        </div>
        <p className="muted small">
          Charged automatically each time you accept an order request routed through the platform. A zero-fee plan or
          no active subscription means these are never charged.
        </p>
        {fees.length === 0 ? (
          <EmptyState title="No service fees yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Charged</th>
                </tr>
              </thead>
              <tbody>
                {fees.map((fee) => (
                  <tr key={fee.id}>
                    <td>{fee.order_reference}</td>
                    <td>${fee.amount}</td>
                    <td>
                      <Badge tone={feeTone(fee.status)}>{fee.status}</Badge>
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
