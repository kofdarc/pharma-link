"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryBatch } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function InventoryDetailPage() {
  const t = useTranslations();
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<InventoryBatch | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<InventoryBatch>(`/pharmacy/inventory/${id}/`).then(setItem).catch(() => setError(t("pharmacyInventoryDetail.notFound")));
  }

  useEffect(load, [id]); // eslint-disable-line react-hooks/exhaustive-deps

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
      setMessage(t("pharmacyInventoryDetail.adjustmentRecorded"));
      event.currentTarget.reset();
    } catch {
      setError(t("pharmacyInventoryDetail.adjustmentFailed"));
    }
  }

  if (!item) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{item.medicine_detail.display_name}</h1>
          <p>{t("pharmacyInventoryDetail.batchLabel", { batch: item.batch_number || t("pharmacyInventoryDetail.notRecorded") })}</p>
        </div>
        <Badge status tone={item.is_expired ? "danger" : item.is_low_stock ? "warning" : "success"}>
          {item.is_expired ? t("pharmacyInventoryDetail.expired") : item.is_low_stock ? t("pharmacyInventoryDetail.lowStock") : t("pharmacyInventoryDetail.available")}
        </Badge>
      </div>
      <section className="metrics-grid">
        <div className="metric-card">
          <span>{t("pharmacyInventoryDetail.currentQuantity")}</span>
          <strong>{item.current_quantity}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyInventoryDetail.expiryDate")}</span>
          <strong style={{ fontSize: "1.1rem" }}>{item.expiry_date || t("pharmacyInventoryDetail.notRecordedCap")}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyInventoryDetail.sellingPrice")}</span>
          <strong>${item.selling_price}</strong>
        </div>
        <div className="metric-card">
          <span>{t("pharmacyInventoryDetail.publicAvailability")}</span>
          <strong style={{ fontSize: "1.1rem" }}>{item.public_availability_enabled ? t("pharmacyInventoryDetail.published") : t("pharmacyInventoryDetail.hidden")}</strong>
        </div>
      </section>
      <form className="toolbar" onSubmit={adjust}>
        <Field label={t("pharmacyInventoryDetail.quantityDelta")}>
          <input name="quantity_delta" type="number" required placeholder={t("pharmacyInventoryDetail.quantityDeltaPlaceholder")} />
        </Field>
        <Field label={t("pharmacyInventoryDetail.reason")}>
          <input name="reason" placeholder={t("pharmacyInventoryDetail.reasonPlaceholder")} />
        </Field>
        <Button type="submit">{t("pharmacyInventoryDetail.recordAdjustment")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}
