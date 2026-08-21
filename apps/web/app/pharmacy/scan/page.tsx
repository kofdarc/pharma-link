"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { PublicPrescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { QrScanner } from "@/components/rx/QrScanner";

/**
 * Same dispense flow as the public /rx page, but from inside the pharmacy workspace so the
 * dispense is attributed to this pharmacy automatically.
 */
export default function PharmacyScanPage() {
  const t = useTranslations();
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [scanning, setScanning] = useState(false);
  const [prescription, setPrescription] = useState<PublicPrescription | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [pharmacistName, setPharmacistName] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function lookup(nextCode: string, key: string, nextPin: string) {
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<PublicPrescription>("/pharmacy/rx/scan/", {
        method: "POST",
        body: JSON.stringify({ code: nextCode, key, pin: nextPin })
      });
      setPrescription(data);
      setQuantities(Object.fromEntries(data.items.map((item) => [item.id, item.quantity_remaining])));
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyScan.lookupFailed"));
    } finally {
      setBusy(false);
    }
  }

  function onScanned(value: string) {
    setScanning(false);
    try {
      const url = new URL(value);
      const parts = url.pathname.split("/").filter(Boolean);
      const scannedCode = parts[parts.length - 1];
      setCode(scannedCode);
      void lookup(scannedCode, url.searchParams.get("k") || "", "");
    } catch {
      setError(t("pharmacyScan.notPharmalinkQr"));
    }
  }

  async function dispense(event: FormEvent) {
    event.preventDefault();
    if (!prescription) return;
    const items = prescription.items
      .filter((item) => (quantities[item.id] || 0) > 0)
      .map((item) => ({ prescription_item: item.id, quantity: quantities[item.id] }));
    if (items.length === 0) {
      setError(t("pharmacyScan.enterQuantity"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await apiFetch<{ prescription_status: string }>("/public/rx/dispense/", {
        method: "POST",
        body: JSON.stringify({
          ticket: prescription.dispense_ticket,
          pharmacist_name: pharmacistName || "Pharmacy staff",
          items
        })
      });
      setDone(
        t("pharmacyScan.recordedMessage", {
          status: result.prescription_status.replace(/_/g, " ").toLowerCase()
        })
      );
      setPrescription(null);
      setCode("");
      setPin("");
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyScan.dispenseFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyScan.title")}</h1>
          <p className="muted">
            {t("pharmacyScan.subtitleBefore")} <Link href="/rx">/rx</Link> {t("pharmacyScan.subtitleAfter")}
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}

      {!prescription ? (
        <section className="panel">
          <div className="rx-entry-grid">
            <div className="rx-entry-card">
              <h3>{t("pharmacyScan.scan")}</h3>
              {scanning ? (
                <QrScanner onResult={onScanned} onError={(msg) => { setScanning(false); setError(msg); }} />
              ) : (
                <Button type="button" onClick={() => { setError(""); setDone(""); setScanning(true); }}>
                  {t("pharmacyScan.openCamera")}
                </Button>
              )}
            </div>
            <div className="rx-entry-card">
              <h3>{t("pharmacyScan.orTypeCode")}</h3>
              <form
                className="stacked-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void lookup(code.trim().toUpperCase(), "", pin.trim());
                }}
              >
                <Field label={t("pharmacyScan.code")}>
                  <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder="RX-XXXX-XXXX" />
                </Field>
                <Field label={t("pharmacyScan.pin")}>
                  <input value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="000000" />
                </Field>
                <Button type="submit" disabled={busy}>
                  {t("pharmacyScan.open")}
                </Button>
              </form>
            </div>
          </div>
        </section>
      ) : (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>{prescription.code}</h2>
              <p className="muted">
                {t("pharmacyScan.prescribedBy", {
                  patient: prescription.patient_name,
                  doctor: prescription.doctor.full_name,
                  license: prescription.doctor.license_number
                })}
              </p>
            </div>
            <Badge tone={prescription.is_consumable ? "success" : "danger"}>{prescription.status.replace(/_/g, " ")}</Badge>
          </div>

          {prescription.diagnosis_note ? (
            <Notice>{t("pharmacyScan.doctorsNote", { note: prescription.diagnosis_note })}</Notice>
          ) : null}
          {prescription.dispense_history.length > 0 ? (
            <Notice>
              {t("pharmacyScan.partlyFilledElsewhere", {
                details: prescription.dispense_history.map((entry) => `${entry.pharmacy_name} (${entry.units} units)`).join(", ")
              })}
            </Notice>
          ) : null}

          <form onSubmit={dispense} className="stacked-form">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyScan.item")}</th>
                  <th>{t("pharmacyScan.instructions")}</th>
                  <th>{t("pharmacyScan.remaining")}</th>
                  <th>{t("pharmacyScan.dispensingNow")}</th>
                </tr>
              </thead>
              <tbody>
                {prescription.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.medicine_text}</strong>
                      {!item.allow_generic_substitution ? (
                        <>
                          <br />
                          <span className="muted small">{t("pharmacyScan.noSubstitution")}</span>
                        </>
                      ) : null}
                    </td>
                    <td className="muted">{item.dosage_instructions || "—"}</td>
                    <td>
                      <strong>
                        {item.quantity_remaining} {item.unit}
                      </strong>
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

            <Field label={t("pharmacyScan.dispensingPharmacist")}>
              <input value={pharmacistName} onChange={(event) => setPharmacistName(event.target.value)} placeholder={t("pharmacyScan.fullName")} />
            </Field>

            <div className="actions">
              <Button type="submit" disabled={busy || !prescription.is_consumable}>
                {busy ? t("pharmacyScan.recording") : t("pharmacyScan.confirmDispense")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setPrescription(null)}>
                {t("pharmacyScan.cancel")}
              </Button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}
