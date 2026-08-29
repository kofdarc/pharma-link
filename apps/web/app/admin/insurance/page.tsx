"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { InsuranceClaim, InsurancePlan, InsuranceProvider, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function claimTone(status: InsuranceClaim["status"]) {
  if (status === "PAID") return "success" as const;
  if (status === "REJECTED") return "danger" as const;
  if (status === "APPROVED") return "info" as const;
  if (status === "CANCELLED") return "neutral" as const;
  return "warning" as const;
}

export default function AdminInsurancePage() {
  const [providers, setProviders] = useState<InsuranceProvider[]>([]);
  const [plans, setPlans] = useState<InsurancePlan[]>([]);
  const [claims, setClaims] = useState<InsuranceClaim[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [providerData, planData, claimData] = await Promise.all([
        apiFetch<Paginated<InsuranceProvider> | InsuranceProvider[]>("/admin/insurance-providers/"),
        apiFetch<Paginated<InsurancePlan> | InsurancePlan[]>("/admin/insurance-plans/"),
        apiFetch<Paginated<InsuranceClaim> | InsuranceClaim[]>("/admin/insurance-claims/")
      ]);
      setProviders(asList(providerData));
      setPlans(asList(planData));
      setClaims(asList(claimData));
    } catch {
      setError("Could not load insurance data.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      await apiFetch("/admin/insurance-providers/", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name"), phone: form.get("phone") })
      });
      setMessage("Provider created.");
      event.currentTarget.reset();
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not create that provider.");
    }
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      await apiFetch("/admin/insurance-plans/", {
        method: "POST",
        body: JSON.stringify({
          provider: form.get("provider"),
          name: form.get("name"),
          coverage_percentage: form.get("coverage_percentage"),
          copay_minimum: form.get("copay_minimum")
        })
      });
      setMessage("Plan created.");
      event.currentTarget.reset();
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not create that plan.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Insurance</h1>
          <p className="muted">Providers, plans, and claims across every pharmacy.</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      <section className="panel">
        <h3>Providers</h3>
        <form className="form-grid" onSubmit={createProvider}>
          <Field label="Name">
            <input name="name" required />
          </Field>
          <Field label="Phone">
            <input name="phone" />
          </Field>
          <Button type="submit">Create provider</Button>
        </form>
        {providers.length === 0 ? (
          <EmptyState title="No insurance providers yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((provider) => (
                  <tr key={provider.id}>
                    <td>{provider.name}</td>
                    <td className="muted">{provider.phone || "—"}</td>
                    <td>
                      <Badge status tone={provider.is_active ? "success" : "neutral"}>{provider.is_active ? "Active" : "Inactive"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Plans</h3>
        <form className="form-grid" onSubmit={createPlan}>
          <Field label="Provider">
            <select name="provider" required>
              <option value="">Select a provider</option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Name">
            <input name="name" required />
          </Field>
          <Field label="Coverage %">
            <input name="coverage_percentage" type="number" step="0.01" min="0" max="100" defaultValue="80" required />
          </Field>
          <Field label="Minimum copay">
            <input name="copay_minimum" type="number" step="0.01" min="0" defaultValue="0" required />
          </Field>
          <Button type="submit">Create plan</Button>
        </form>
        {plans.length === 0 ? (
          <EmptyState title="No insurance plans yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Name</th>
                  <th>Coverage</th>
                  <th>Minimum copay</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.provider_name}</td>
                    <td>{plan.name}</td>
                    <td>{plan.coverage_percentage}%</td>
                    <td>${plan.copay_minimum}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Claims</h3>
        {claims.length === 0 ? (
          <EmptyState title="No insurance claims yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Pharmacy</th>
                  <th>Source</th>
                  <th>Patient</th>
                  <th>Billed</th>
                  <th>Covered</th>
                  <th>Copay</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr key={claim.id}>
                    <td>{claim.pharmacy_name}</td>
                    <td>{claim.order_reference || claim.invoice_number}</td>
                    <td>{claim.policy_detail.holder_name}</td>
                    <td>${claim.billed_amount}</td>
                    <td>${claim.covered_amount}</td>
                    <td>${claim.patient_copay}</td>
                    <td>
                      <Badge status tone={claimTone(claim.status)}>{claim.status}</Badge>
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
