"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { Paginated, Pharmacy, PharmacySubscription, PlatformRevenueOverview, PlatformServiceFee, SubscriptionPlan } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function feeTone(status: PlatformServiceFee["status"]) {
  if (status === "PAID") return "success" as const;
  if (status === "WAIVED") return "neutral" as const;
  return "warning" as const;
}

export default function AdminBillingPage() {
  const [overview, setOverview] = useState<PlatformRevenueOverview | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [subscriptions, setSubscriptions] = useState<PharmacySubscription[]>([]);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [fees, setFees] = useState<PlatformServiceFee[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [overviewData, planData, subscriptionData, pharmacyData, feeData] = await Promise.all([
        apiFetch<PlatformRevenueOverview>("/admin/revenue/overview/"),
        apiFetch<Paginated<SubscriptionPlan> | SubscriptionPlan[]>("/admin/subscription-plans/"),
        apiFetch<Paginated<PharmacySubscription> | PharmacySubscription[]>("/admin/pharmacy-subscriptions/"),
        apiFetch<Paginated<Pharmacy> | Pharmacy[]>("/admin/pharmacies/"),
        apiFetch<Paginated<PlatformServiceFee> | PlatformServiceFee[]>("/admin/service-fees/")
      ]);
      setOverview(overviewData);
      setPlans(asList(planData));
      setSubscriptions(asList(subscriptionData));
      setPharmacies(asList(pharmacyData));
      setFees(asList(feeData));
    } catch {
      setError("Could not load billing data.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      await apiFetch("/admin/subscription-plans/", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          monthly_fee: form.get("monthly_fee"),
          service_fee_per_request: form.get("service_fee_per_request")
        })
      });
      setMessage("Plan created.");
      event.currentTarget.reset();
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not create that plan.");
    }
  }

  async function assignSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const pharmacy = String(form.get("pharmacy") || "");
    const plan = String(form.get("plan") || "");
    if (!pharmacy || !plan) return;
    setError("");
    try {
      const existing = subscriptions.find((entry) => entry.pharmacy === pharmacy);
      if (existing) {
        await apiFetch(`/admin/pharmacy-subscriptions/${existing.id}/`, { method: "PATCH", body: JSON.stringify({ plan, status: "ACTIVE" }) });
      } else {
        await apiFetch("/admin/pharmacy-subscriptions/", { method: "POST", body: JSON.stringify({ pharmacy, plan }) });
      }
      setMessage("Subscription saved.");
      event.currentTarget.reset();
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not save that subscription.");
    }
  }

  async function markPaid(fee: PlatformServiceFee) {
    setError("");
    try {
      await apiFetch(`/admin/service-fees/${fee.id}/mark-paid/`, { method: "POST" });
      setMessage(`Marked ${fee.pharmacy_name}'s fee for ${fee.order_reference} paid.`);
      void load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Billing</h1>
          <p className="muted">Subscription plans, pharmacy assignments, and platform revenue.</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      <section className="metric-grid">
        <div className="metric-card">
          <span>Active subscriptions</span>
          <strong>{overview?.active_subscriptions ?? 0}</strong>
        </div>
        <div className="metric-card metric-card-good">
          <span>Monthly recurring revenue</span>
          <strong>${overview?.monthly_recurring_revenue ?? "0.00"}</strong>
        </div>
        <div className="metric-card metric-card-good">
          <span>Service fees collected</span>
          <strong>${overview?.service_fees_collected ?? "0.00"}</strong>
        </div>
        <div className="metric-card">
          <span>Service fees pending</span>
          <strong>${overview?.service_fees_pending ?? "0.00"}</strong>
          <small className="muted">{overview?.service_fee_requests ?? 0} request(s) total</small>
        </div>
      </section>

      <section className="panel">
        <h3>Subscription plans</h3>
        <form className="form-grid" onSubmit={createPlan}>
          <Field label="Name">
            <input name="name" required />
          </Field>
          <Field label="Monthly fee">
            <input name="monthly_fee" type="number" step="0.01" min="0" defaultValue="0" required />
          </Field>
          <Field label="Per-request fee">
            <input name="service_fee_per_request" type="number" step="0.01" min="0" defaultValue="0" required />
          </Field>
          <Button type="submit">Create plan</Button>
        </form>
        {plans.length === 0 ? (
          <EmptyState title="No plans yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Monthly fee</th>
                  <th>Per-request fee</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.name}</td>
                    <td>${plan.monthly_fee}</td>
                    <td>${plan.service_fee_per_request}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Pharmacy subscriptions</h3>
        <form className="form-grid" onSubmit={assignSubscription}>
          <Field label="Pharmacy">
            <select name="pharmacy" required>
              <option value="">Select a pharmacy</option>
              {pharmacies.map((pharmacy) => (
                <option key={pharmacy.id} value={pharmacy.id}>
                  {pharmacy.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Plan">
            <select name="plan" required>
              <option value="">Select a plan</option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name}
                </option>
              ))}
            </select>
          </Field>
          <Button type="submit">Assign</Button>
        </form>
        {subscriptions.length === 0 ? (
          <EmptyState title="No pharmacy is subscribed to a plan yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Pharmacy</th>
                  <th>Plan</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {subscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>{subscription.pharmacy_name}</td>
                    <td>{subscription.plan_detail.name}</td>
                    <td>
                      <Badge status tone={subscription.status === "ACTIVE" ? "success" : subscription.status === "PAST_DUE" ? "warning" : "neutral"}>
                        {subscription.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Service fees</h3>
        {fees.length === 0 ? (
          <EmptyState title="No service fees yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Pharmacy</th>
                  <th>Order</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {fees.map((fee) => (
                  <tr key={fee.id}>
                    <td>{fee.pharmacy_name}</td>
                    <td>{fee.order_reference}</td>
                    <td>${fee.amount}</td>
                    <td>
                      <Badge status tone={feeTone(fee.status)}>{fee.status}</Badge>
                    </td>
                    <td>
                      {fee.status === "PENDING" ? (
                        <Button type="button" variant="secondary" onClick={() => markPaid(fee)}>
                          Mark paid
                        </Button>
                      ) : null}
                    </td>
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
