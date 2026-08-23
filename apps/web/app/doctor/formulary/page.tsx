"use client";

import { FormEvent, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { PublicInsurancePlan } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

/**
 * PrescribeIT's "Formulary Services" checks per-medicine coverage against a formulary
 * dataset this platform does not have (see InsurancePlan's docstring). This surfaces the
 * closest real signal instead: the named patient's own known insurance plan and its
 * plan-level coverage, so a doctor can gauge affordability before prescribing.
 */
export default function DoctorFormularyPage() {
  const t = useTranslations();
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [plans, setPlans] = useState<PublicInsurancePlan[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function lookup(event: FormEvent) {
    event.preventDefault();
    if (!email.trim() && !phone.trim()) {
      setError(t("doctorFormulary.provideOne"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (email.trim()) params.set("patient_email", email.trim());
      if (phone.trim()) params.set("patient_phone", phone.trim());
      const result = await apiFetch<PublicInsurancePlan[]>(`/doctor/formulary/lookup/?${params.toString()}`);
      setPlans(result);
    } catch (exception) {
      setError((exception as ApiError).message || t("doctorFormulary.lookupFailed"));
      setPlans(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("doctorFormulary.title")}</h1>
          <p className="muted">{t("doctorFormulary.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <form className="panel form-grid" onSubmit={lookup}>
        <Field label={t("doctorFormulary.patientEmail")}>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label={t("doctorFormulary.patientPhone")}>
          <input value={phone} onChange={(event) => setPhone(event.target.value)} />
        </Field>
        <Button type="submit" disabled={busy}>
          {busy ? t("doctorFormulary.checking") : t("doctorFormulary.checkCoverage")}
        </Button>
      </form>

      {plans !== null ? (
        plans.length === 0 ? (
          <EmptyState title={t("doctorFormulary.noPolicy")} detail={t("doctorFormulary.noPolicyHint")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("doctorFormulary.provider")}</th>
                  <th>{t("doctorFormulary.plan")}</th>
                  <th>{t("doctorFormulary.coverage")}</th>
                  <th>{t("doctorFormulary.copayMinimum")}</th>
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
        )
      ) : null}
    </>
  );
}
