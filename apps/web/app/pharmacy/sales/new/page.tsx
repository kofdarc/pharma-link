"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Client, Medicine, Paginated, PatientInsurancePolicy } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function NewSalePage() {
  const t = useTranslations();
  const router = useRouter();
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [lines, setLines] = useState([{ medicine: "", quantity: 1, unit_price: "", discount: "0" }]);
  const [error, setError] = useState("");
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [policies, setPolicies] = useState<PatientInsurancePolicy[]>([]);
  const [insurancePolicyId, setInsurancePolicyId] = useState("");

  useEffect(() => {
    apiFetch<Medicine[] | { results: Medicine[] }>("/medicines/search/?q=").then((payload) => setMedicines(asList(payload)));
  }, []);

  useEffect(() => {
    apiFetch<Paginated<Client> | Client[]>("/pharmacy/clients/")
      .then((payload) => setClients(asList(payload)))
      .catch(() => setClients([]));
  }, []);

  useEffect(() => {
    setInsurancePolicyId("");
    if (!clientId) {
      setPolicies([]);
      setPaymentMethod((current) => (current === "ON_ACCOUNT" ? "CASH" : current));
      return;
    }
    apiFetch<Paginated<PatientInsurancePolicy> | PatientInsurancePolicy[]>(`/pharmacy/insurance-policies/?client=${clientId}`)
      .then((payload) => setPolicies(asList(payload)))
      .catch(() => setPolicies([]));
  }, [clientId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const sale = await apiFetch<{ id: string }>("/pharmacy/sales/", {
        method: "POST",
        body: JSON.stringify({
          items: lines.map((line) => ({
            medicine: line.medicine,
            quantity: Number(line.quantity),
            unit_price: line.unit_price || undefined,
            discount: line.discount || "0"
          })),
          client: clientId || undefined,
          payment_method: paymentMethod,
          insurance_policy: insurancePolicyId || undefined
        })
      });
      router.push(`/pharmacy/invoices/${sale.id}`);
    } catch {
      setError(t("pharmacySalesNew.saleFailed"));
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{t("pharmacySalesNew.title")}</h1>
          <p>{t("pharmacySalesNew.subtitle")}</p>
        </div>
      </div>
      <form onSubmit={submit}>
        <div className="form-grid" style={{ marginBottom: 12 }}>
          <Field label={t("pharmacySalesNew.client")}>
            <select value={clientId} onChange={(event) => setClientId(event.target.value)}>
              <option value="">{t("pharmacySalesNew.walkIn")}</option>
              {clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.full_name} — {client.phone}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("pharmacySalesNew.paymentMethod")}>
            <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}>
              <option value="CASH">Cash</option>
              <option value="CARD">Card</option>
              {clientId ? <option value="ON_ACCOUNT">On account</option> : null}
              <option value="OTHER">Other</option>
            </select>
          </Field>
          {policies.length > 0 ? (
            <Field label={t("pharmacySalesNew.insurancePolicy")}>
              <select value={insurancePolicyId} onChange={(event) => setInsurancePolicyId(event.target.value)}>
                <option value="">{t("pharmacySalesNew.noInsurance")}</option>
                {policies.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policy.plan_detail.provider_name} — {policy.plan_detail.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
        </div>
        {lines.map((line, index) => (
          <div className="form-grid" key={index} style={{ marginBottom: 12 }}>
            <Field label={t("pharmacySalesNew.medicine")}>
              <select value={line.medicine} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, medicine: event.target.value } : row)))} required>
                <option value="">{t("pharmacySalesNew.selectMedicine")}</option>
                {medicines.map((medicine) => (
                  <option key={medicine.id} value={medicine.id}>
                    {medicine.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("pharmacySalesNew.quantity")}>
              <input type="number" min="1" value={line.quantity} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, quantity: Number(event.target.value) } : row)))} required />
            </Field>
            <Field label={t("pharmacySalesNew.unitPrice")}>
              <input type="number" step="0.01" min="0" value={line.unit_price} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, unit_price: event.target.value } : row)))} />
            </Field>
            <Field label={t("pharmacySalesNew.discount")}>
              <input type="number" step="0.01" min="0" value={line.discount} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, discount: event.target.value } : row)))} />
            </Field>
          </div>
        ))}
        <div className="actions">
          <Button type="button" variant="secondary" onClick={() => setLines([...lines, { medicine: "", quantity: 1, unit_price: "", discount: "0" }])}>
            {t("pharmacySalesNew.addLine")}
          </Button>
          <Button type="submit">{t("pharmacySalesNew.confirmSale")}</Button>
        </div>
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

