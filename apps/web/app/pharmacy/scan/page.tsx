"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
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
      setError((exception as ApiError).message || "Could not open that prescription.");
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
      setError("That QR code is not a MediSync prescription.");
    }
  }

  async function dispense(event: FormEvent) {
    event.preventDefault();
    if (!prescription) return;
    const items = prescription.items
      .filter((item) => (quantities[item.id] || 0) > 0)
      .map((item) => ({ prescription_item: item.id, quantity: quantities[item.id] }));
    if (items.length === 0) {
      setError("Enter at least one quantity.");
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
      setDone(`Recorded. The prescription is now ${result.prescription_status.replace(/_/g, " ").toLowerCase()}.`);
      setPrescription(null);
      setCode("");
      setPin("");
    } catch (exception) {
      setError((exception as ApiError).message || "Could not record the dispense.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Scan a prescription</h1>
          <p className="muted">
            Dispensing from here is attributed to your pharmacy and appears in your records. The same prescription
            can also be consumed by any pharmacy at <Link href="/rx">/rx</Link> without an account.
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {done ? <Notice tone="success">{done}</Notice> : null}

      {!prescription ? (
        <section className="panel">
          <div className="rx-entry-grid">
            <div className="rx-entry-card">
              <h3>Scan</h3>
              {scanning ? (
                <QrScanner onResult={onScanned} onError={(msg) => { setScanning(false); setError(msg); }} />
              ) : (
                <Button type="button" onClick={() => { setError(""); setDone(""); setScanning(true); }}>
                  Open camera
                </Button>
              )}
            </div>
            <div className="rx-entry-card">
              <h3>Or type the code and PIN</h3>
              <form
                className="stacked-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void lookup(code.trim().toUpperCase(), "", pin.trim());
                }}
              >
                <Field label="Code">
                  <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder="RX-XXXX-XXXX" />
                </Field>
                <Field label="PIN">
                  <input value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="000000" />
                </Field>
                <Button type="submit" disabled={busy}>
                  Open
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
                {prescription.patient_name} · prescribed by Dr. {prescription.doctor.full_name} (
                {prescription.doctor.license_number})
              </p>
            </div>
            <Badge tone={prescription.is_consumable ? "success" : "danger"}>{prescription.status.replace(/_/g, " ")}</Badge>
          </div>

          {prescription.diagnosis_note ? <Notice>Doctor&apos;s note: {prescription.diagnosis_note}</Notice> : null}
          {prescription.dispense_history.length > 0 ? (
            <Notice>
              Already partly filled elsewhere:{" "}
              {prescription.dispense_history.map((entry) => `${entry.pharmacy_name} (${entry.units} units)`).join(", ")}
            </Notice>
          ) : null}

          <form onSubmit={dispense} className="stacked-form">
            <table className="table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Instructions</th>
                  <th>Remaining</th>
                  <th>Dispensing now</th>
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
                          <span className="muted small">No substitution allowed</span>
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

            <Field label="Dispensing pharmacist">
              <input value={pharmacistName} onChange={(event) => setPharmacistName(event.target.value)} placeholder="Full name" />
            </Field>

            <div className="actions">
              <Button type="submit" disabled={busy || !prescription.is_consumable}>
                {busy ? "Recording..." : "Confirm dispense"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setPrescription(null)}>
                Cancel
              </Button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}
