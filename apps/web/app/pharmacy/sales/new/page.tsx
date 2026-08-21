"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Medicine } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function NewSalePage() {
  const t = useTranslations();
  const router = useRouter();
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [lines, setLines] = useState([{ medicine: "", quantity: 1, unit_price: "", discount: "0" }]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Medicine[] | { results: Medicine[] }>("/medicines/search/?q=").then((payload) => setMedicines(asList(payload)));
  }, []);

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
          payment_method: "CASH"
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

