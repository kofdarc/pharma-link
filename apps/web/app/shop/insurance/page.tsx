"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, PatientInsurancePolicy, PublicInsurancePlan } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function ShopInsurancePage() {
  const t = useTranslations();
  const [policies, setPolicies] = useState<PatientInsurancePolicy[]>([]);
  const [plans, setPlans] = useState<PublicInsurancePlan[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ plan: "", member_id: "", holder_name: "", valid_until: "" });

  const load = useCallback(() => {
    apiFetch<Paginated<PatientInsurancePolicy> | PatientInsurancePolicy[]>("/shop/insurance-policies/")
      .then((payload) => setPolicies(asList(payload)))
      .catch(() => setError(t("shopInsurance.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    apiFetch<PublicInsurancePlan[]>("/public/insurance-plans/")
      .then(setPlans)
      .catch(() => setPlans([]));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiFetch("/shop/insurance-policies/", {
        method: "POST",
        body: JSON.stringify({ ...form, valid_until: form.valid_until || null })
      });
      setForm({ plan: "", member_id: "", holder_name: "", valid_until: "" });
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("shopInsurance.saveError"));
    } finally {
      setBusy(false);
    }
  }

  async function remove(policy: PatientInsurancePolicy) {
    setError("");
    try {
      await apiFetch(`/shop/insurance-policies/${policy.id}/`, { method: "DELETE" });
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("shopInsurance.removeError"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("shopInsurance.title")}</h1>
          <p className="muted">{t("shopInsurance.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {policies.length === 0 ? <EmptyState title={t("shopInsurance.noPolicies")} /> : null}

      <div className="result-grid">
        {policies.map((policy) => (
          <article className="result-card" key={policy.id}>
            <h3>{policy.plan_detail.provider_name}</h3>
            <p className="muted small">{policy.plan_detail.name}</p>
            <p>{policy.holder_name}</p>
            <p className="muted small">{policy.member_id}</p>
            <p className="muted small">
              {t("shopInsurance.coverage", { percentage: policy.plan_detail.coverage_percentage, minimum: `$${policy.plan_detail.copay_minimum}` })}
            </p>
            <Button type="button" variant="secondary" onClick={() => remove(policy)}>
              {t("shopInsurance.remove")}
            </Button>
          </article>
        ))}
      </div>

      <section className="panel">
        <h3>{t("shopInsurance.addPolicy")}</h3>
        <form className="form-grid" onSubmit={submit}>
          <Field label={t("shopInsurance.plan")}>
            <select value={form.plan} onChange={(event) => setForm({ ...form, plan: event.target.value })} required>
              <option value="">{t("shopInsurance.selectPlan")}</option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.provider_name} — {plan.name} ({plan.coverage_percentage}%)
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("shopInsurance.memberId")}>
            <input value={form.member_id} onChange={(event) => setForm({ ...form, member_id: event.target.value })} required />
          </Field>
          <Field label={t("shopInsurance.holderName")}>
            <input value={form.holder_name} onChange={(event) => setForm({ ...form, holder_name: event.target.value })} required />
          </Field>
          <Field label={t("shopInsurance.validUntil")}>
            <input type="date" value={form.valid_until} onChange={(event) => setForm({ ...form, valid_until: event.target.value })} />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? t("shopInsurance.saving") : t("shopInsurance.savePolicy")}
          </Button>
        </form>
      </section>
    </>
  );
}
