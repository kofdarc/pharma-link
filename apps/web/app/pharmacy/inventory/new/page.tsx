"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Medicine } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function NewInventoryBatchPage() {
  const t = useTranslations();
  const router = useRouter();
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Medicine[] | { results: Medicine[] }>("/medicines/search/?q=").then((payload) => setMedicines(asList(payload)));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const created = await apiFetch<{ id: string }>("/pharmacy/inventory/", {
        method: "POST",
        body: JSON.stringify({
          medicine: form.get("medicine"),
          batch_number: form.get("batch_number"),
          initial_quantity: Number(form.get("initial_quantity")),
          expiry_date: form.get("expiry_date") || null,
          supplier_name: form.get("supplier_name"),
          purchase_cost: form.get("purchase_cost") || null,
          selling_price: form.get("selling_price"),
          low_stock_threshold: Number(form.get("low_stock_threshold") || 5),
          public_availability_enabled: form.get("public_availability_enabled") === "on"
        })
      });
      router.push(`/pharmacy/inventory/${created.id}`);
    } catch {
      setError(t("pharmacyInventoryNew.saveFailed"));
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{t("pharmacyInventoryNew.title")}</h1>
          <p>{t("pharmacyInventoryNew.subtitle")}</p>
        </div>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <Field label={t("pharmacyInventoryNew.medicine")}>
          <select name="medicine" required>
            <option value="">{t("pharmacyInventoryNew.selectMedicine")}</option>
            {medicines.map((medicine) => (
              <option key={medicine.id} value={medicine.id}>
                {medicine.display_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("pharmacyInventoryNew.batchNumber")}>
          <input name="batch_number" />
        </Field>
        <Field label={t("pharmacyInventoryNew.quantity")}>
          <input name="initial_quantity" type="number" min="0" required />
        </Field>
        <Field label={t("pharmacyInventoryNew.expiryDate")}>
          <input name="expiry_date" type="date" />
        </Field>
        <Field label={t("pharmacyInventoryNew.supplier")}>
          <input name="supplier_name" />
        </Field>
        <Field label={t("pharmacyInventoryNew.purchaseCost")}>
          <input name="purchase_cost" type="number" step="0.01" min="0" />
        </Field>
        <Field label={t("pharmacyInventoryNew.sellingPrice")}>
          <input name="selling_price" type="number" step="0.01" min="0" required />
        </Field>
        <Field label={t("pharmacyInventoryNew.lowStockThreshold")}>
          <input name="low_stock_threshold" type="number" min="0" defaultValue="5" />
        </Field>
        <label className="field">
          <span>{t("pharmacyInventoryNew.publicAvailability")}</span>
          <input name="public_availability_enabled" type="checkbox" defaultChecked />
        </label>
        <Button type="submit">{t("pharmacyInventoryNew.saveBatch")}</Button>
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

