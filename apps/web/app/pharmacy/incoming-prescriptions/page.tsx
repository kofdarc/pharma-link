"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, Prescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ChatPanel } from "@/components/messaging/ChatPanel";

function tone(status: string) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

/**
 * PrescribeIT's "Create Rx" model: a doctor sends a prescription straight to this pharmacy
 * instead of the patient carrying a QR/PIN. This is the pharmacy's inbox for that - dispense
 * needs no ticket here, since being in this list already proves the pharmacy is the target.
 */
export default function PharmacyIncomingPrescriptionsPage() {
  const t = useTranslations();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [pharmacistName, setPharmacistName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<Paginated<Prescription> | Prescription[]>("/pharmacy/incoming-prescriptions/")
      .then((payload) => setPrescriptions(asList(payload)))
      .catch(() => setError(t("pharmacyIncoming.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  function toggle(prescription: Prescription) {
    if (openId === prescription.id) {
      setOpenId(null);
      return;
    }
    setOpenId(prescription.id);
    setQuantities(Object.fromEntries(prescription.items.map((item) => [item.id, item.quantity_remaining])));
  }

  async function dispense(prescription: Prescription) {
    const items = prescription.items
      .filter((item) => (quantities[item.id] || 0) > 0)
      .map((item) => ({ prescription_item: item.id, quantity: quantities[item.id] }));
    if (items.length === 0) {
      setError(t("pharmacyIncoming.enterQuantity"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiFetch(`/pharmacy/incoming-prescriptions/${prescription.id}/dispense/`, {
        method: "POST",
        body: JSON.stringify({ pharmacist_name: pharmacistName || "Pharmacy staff", items })
      });
      setMessage(t("pharmacyIncoming.dispensed", { code: prescription.code }));
      setOpenId(null);
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyIncoming.dispenseFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function requestRenewal(prescription: Prescription) {
    const note = window.prompt(t("pharmacyIncoming.renewalNotePrompt")) || "";
    setError("");
    try {
      await apiFetch("/pharmacy/renewal-requests/", { method: "POST", body: JSON.stringify({ prescription: prescription.id, note }) });
      setMessage(t("pharmacyIncoming.renewalRequested", { code: prescription.code }));
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyIncoming.renewalRequestFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyIncoming.title")}</h1>
          <p className="muted">{t("pharmacyIncoming.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {loading ? <div className="skeleton-card" /> : null}

      {!loading && prescriptions.length === 0 ? <EmptyState title={t("pharmacyIncoming.empty")} detail={t("pharmacyIncoming.emptyHint")} /> : null}

      {prescriptions.map((prescription) => (
        <section key={prescription.id} className="panel">
          <div className="section-header">
            <div>
              <h3>
                <code>{prescription.code}</code>
              </h3>
              <p className="muted small">
                {prescription.patient_name} · {prescription.doctor_name} ({prescription.doctor_license})
              </p>
            </div>
            <div className="toolbar">
              <Badge tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
              {prescription.renewed_from_code ? (
                <span className="muted small">{t("pharmacyIncoming.renewalOf", { code: prescription.renewed_from_code })}</span>
              ) : null}
            </div>
          </div>

          {prescription.diagnosis_note ? <Notice>{prescription.diagnosis_note}</Notice> : null}

          <ul className="clean-list">
            {prescription.items.map((item) => (
              <li key={item.id}>
                <strong>{item.medicine_text}</strong> — {item.quantity_remaining}/{item.quantity_prescribed} {item.unit} {t("pharmacyIncoming.remaining")}
                {item.dosage_instructions ? ` · ${item.dosage_instructions}` : ""}
              </li>
            ))}
          </ul>

          <div className="toolbar">
            {prescription.is_consumable ? (
              <Button type="button" variant="secondary" onClick={() => toggle(prescription)}>
                {openId === prescription.id ? t("pharmacyIncoming.close") : t("pharmacyIncoming.dispense")}
              </Button>
            ) : null}
            <Button type="button" variant="secondary" onClick={() => requestRenewal(prescription)}>
              {t("pharmacyIncoming.requestRenewal")}
            </Button>
            <ChatPanel basePath="/pharmacy/prescriptions" orderFulfillmentId={prescription.id} />
          </div>

          {openId === prescription.id ? (
            <div className="stacked-form">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("pharmacyIncoming.item")}</th>
                    <th>{t("pharmacyIncoming.remaining")}</th>
                    <th>{t("pharmacyIncoming.dispensingNow")}</th>
                  </tr>
                </thead>
                <tbody>
                  {prescription.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.medicine_text}</td>
                      <td>
                        {item.quantity_remaining} {item.unit}
                      </td>
                      <td>
                        <input
                          type="number"
                          min={0}
                          max={item.quantity_remaining}
                          className="qty-input"
                          value={quantities[item.id] ?? 0}
                          onChange={(event) =>
                            setQuantities((current) => ({
                              ...current,
                              [item.id]: Math.max(0, Math.min(item.quantity_remaining, Number(event.target.value) || 0))
                            }))
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Field label={t("pharmacyIncoming.dispensingPharmacist")}>
                <input value={pharmacistName} onChange={(event) => setPharmacistName(event.target.value)} />
              </Field>
              <Button type="button" disabled={busy} onClick={() => dispense(prescription)}>
                {busy ? t("pharmacyIncoming.recording") : t("pharmacyIncoming.confirmDispense")}
              </Button>
            </div>
          ) : null}
        </section>
      ))}
    </>
  );
}
