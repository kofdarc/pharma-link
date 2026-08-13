"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import type { Medicine } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function NewSalePage() {
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
      setError("Sale failed. Check stock availability and line item details.");
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>Create sale</h1>
          <p>Stock is deducted using earliest expiry first. Insufficient stock blocks the sale.</p>
        </div>
      </div>
      <form onSubmit={submit}>
        {lines.map((line, index) => (
          <div className="form-grid" key={index} style={{ marginBottom: 12 }}>
            <Field label="Medicine">
              <select value={line.medicine} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, medicine: event.target.value } : row)))} required>
                <option value="">Select medicine</option>
                {medicines.map((medicine) => (
                  <option key={medicine.id} value={medicine.id}>
                    {medicine.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Quantity">
              <input type="number" min="1" value={line.quantity} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, quantity: Number(event.target.value) } : row)))} required />
            </Field>
            <Field label="Unit price">
              <input type="number" step="0.01" min="0" value={line.unit_price} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, unit_price: event.target.value } : row)))} />
            </Field>
            <Field label="Discount">
              <input type="number" step="0.01" min="0" value={line.discount} onChange={(event) => setLines(lines.map((row, i) => (i === index ? { ...row, discount: event.target.value } : row)))} />
            </Field>
          </div>
        ))}
        <div className="actions">
          <Button type="button" variant="secondary" onClick={() => setLines([...lines, { medicine: "", quantity: 1, unit_price: "", discount: "0" }])}>
            Add line
          </Button>
          <Button type="submit">Confirm sale</Button>
        </div>
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

