"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import type { InventoryBatch } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function InventoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<InventoryBatch | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryBatch>(`/pharmacy/inventory/${id}/`).then(setItem).catch(() => setError("Batch not found or unauthorized."));
  }

  useEffect(load, [id]);

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setMessage("");
    try {
      const updated = await apiFetch<InventoryBatch>(`/pharmacy/inventory/${id}/adjust/`, {
        method: "POST",
        body: JSON.stringify({ quantity_delta: Number(form.get("quantity_delta")), reason: form.get("reason") })
      });
      setItem(updated);
      setMessage("Stock adjustment recorded.");
      event.currentTarget.reset();
    } catch {
      setError("Adjustment failed. Quantity cannot become negative.");
    }
  }

  if (!item) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{item.medicine_detail.display_name}</h1>
          <p>Batch {item.batch_number || "not recorded"}</p>
        </div>
        <Badge tone={item.is_expired ? "danger" : item.is_low_stock ? "warning" : "success"}>{item.is_expired ? "Expired" : item.is_low_stock ? "Low stock" : "Available"}</Badge>
      </div>
      <section className="metrics-grid">
        <div className="metric-card">
          <span>Current quantity</span>
          <strong>{item.current_quantity}</strong>
        </div>
        <div className="metric-card">
          <span>Expiry date</span>
          <strong style={{ fontSize: "1.1rem" }}>{item.expiry_date || "Not recorded"}</strong>
        </div>
        <div className="metric-card">
          <span>Selling price</span>
          <strong>${item.selling_price}</strong>
        </div>
        <div className="metric-card">
          <span>Public availability</span>
          <strong style={{ fontSize: "1.1rem" }}>{item.public_availability_enabled ? "Published" : "Hidden"}</strong>
        </div>
      </section>
      <form className="toolbar" onSubmit={adjust}>
        <Field label="Quantity delta">
          <input name="quantity_delta" type="number" required placeholder="-2 or 10" />
        </Field>
        <Field label="Reason">
          <input name="reason" placeholder="Manual count correction" />
        </Field>
        <Button type="submit">Record adjustment</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

