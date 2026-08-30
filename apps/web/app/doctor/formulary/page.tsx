"use client";

import { FormEvent, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Medicine, PublicInsurancePlan } from "@/types/api";
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

  const [drugQuery, setDrugQuery] = useState("");
  const [drugResults, setDrugResults] = useState<Medicine[] | null>(null);
  const [drugBusy, setDrugBusy] = useState(false);
  const [drugError, setDrugError] = useState("");

  async function lookupDrug(event: FormEvent) {
    event.preventDefault();
    if (!drugQuery.trim()) return;
    setDrugBusy(true);
    setDrugError("");
    try {
      const result = await apiFetch<Medicine[]>(`/medicines/search/?q=${encodeURIComponent(drugQuery.trim())}`);
      setDrugResults(result);
    } catch (exception) {
      setDrugError((exception as ApiError).message || t("doctorFormulary.lookupFailed"));
      setDrugResults(null);
    } finally {
      setDrugBusy(false);
    }
  }

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

      <div className="section-header" style={{ marginTop: 32 }}>
        <div>
          <h2>{t("doctorFormulary.nssfTitle")}</h2>
          <p className="muted">{t("doctorFormulary.nssfSubtitle")}</p>
        </div>
      </div>

      {drugError ? <Notice tone="danger">{drugError}</Notice> : null}

      <form className="panel form-grid" onSubmit={lookupDrug}>
        <Field label={t("doctorFormulary.nssfSearchLabel")}>
          <input value={drugQuery} onChange={(event) => setDrugQuery(event.target.value)} placeholder={t("doctorFormulary.nssfSearchPlaceholder")} />
        </Field>
        <Button type="submit" disabled={drugBusy}>
          {drugBusy ? t("doctorFormulary.checking") : t("doctorFormulary.nssfCheck")}
        </Button>
      </form>

      {drugResults !== null ? (
        drugResults.length === 0 ? (
          <EmptyState title={t("doctorFormulary.nssfNoMatch")} detail={t("doctorFormulary.nssfNoMatchHint")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("doctorFormulary.nssfMedicine")}</th>
                  <th>{t("doctorFormulary.nssfCoverage")}</th>
                  <th>{t("doctorFormulary.nssfRate")}</th>
                  <th>{t("doctorFormulary.nssfReferencePrice")}</th>
                </tr>
              </thead>
              <tbody>
                {drugResults.map((medicine) => (
                  <tr key={medicine.id}>
                    <td>{medicine.display_name}</td>
                    <td>{medicine.nssf_covered ? t("doctorFormulary.nssfCovered") : t("doctorFormulary.nssfNotCovered")}</td>
                    <td>{medicine.nssf_covered && medicine.nssf_reimbursement_rate ? `${medicine.nssf_reimbursement_rate}%` : "—"}</td>
                    <td>{medicine.nssf_covered && medicine.nssf_reference_price ? `$${medicine.nssf_reference_price}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )
      ) : null}

      <p className="muted" style={{ marginTop: 12, fontSize: "0.8125rem" }}>
        {t("doctorFormulary.nssfDisclaimer")}
      </p>
    </>
  );
}
