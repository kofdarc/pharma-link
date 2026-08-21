"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import type { PublicPrescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { BrandMark } from "@/components/ui/BrandMark";

type Result = { dispense_id: string; prescription_status: string; pharmacy_name: string; remaining: { id: string; medicine_text: string; quantity_remaining: number }[] };

function statusTone(status: string) {
  if (status === "FULLY_DISPENSED") return "success";
  if (status === "PARTIALLY_DISPENSED") return "warning";
  if (status === "CANCELLED" || status === "EXPIRED") return "danger";
  return "info";
}

function PrescriptionView() {
  const params = useParams<{ code: string }>();
  const search = useSearchParams();
  const code = decodeURIComponent(params.code);
  const key = search.get("k") || "";
  const pinFromLink = search.get("pin") || "";

  const [prescription, setPrescription] = useState<PublicPrescription | null>(null);
  const [pin, setPin] = useState(pinFromLink);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [needsPin, setNeedsPin] = useState(!key && !pinFromLink);

  // Dispense form state
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [pharmacyName, setPharmacyName] = useState("");
  const [pharmacistName, setPharmacistName] = useState("");
  const [pharmacistLicense, setPharmacistLicense] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  const lookup = useCallback(
    async (withPin: string) => {
      setLoading(true);
      setError("");
      try {
        const data = await apiFetch<PublicPrescription>("/public/rx/lookup/", {
          method: "POST",
          body: JSON.stringify({ code, key, pin: withPin })
        });
        setPrescription(data);
        setNeedsPin(false);
        // Pre-fill each line with everything still owed: the common case is dispensing in full.
        setQuantities(Object.fromEntries(data.items.map((item) => [item.id, item.quantity_remaining])));
      } catch (exception) {
        const apiError = exception as ApiError;
        setError(apiError.message || "Could not open this prescription.");
        setNeedsPin(true);
      } finally {
        setLoading(false);
      }
    },
    [code, key]
  );

  useEffect(() => {
    if (key || pinFromLink) void lookup(pinFromLink);
  }, [key, pinFromLink, lookup]);

  async function submitDispense(event: FormEvent) {
    event.preventDefault();
    if (!prescription) return;
    const items = prescription.items
      .filter((item) => (quantities[item.id] || 0) > 0)
      .map((item) => ({ prescription_item: item.id, quantity: quantities[item.id] }));
    if (items.length === 0) {
      setError("Enter at least one quantity to dispense.");
      return;
    }
    if (!prescription.pharmacy && !pharmacyName.trim()) {
      setError("Enter your pharmacy name.");
      return;
    }
    if (!pharmacistName.trim()) {
      setError("Enter the dispensing pharmacist's name.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const data = await apiFetch<Result>("/public/rx/dispense/", {
        method: "POST",
        body: JSON.stringify({
          ticket: prescription.dispense_ticket,
          pharmacy_name: pharmacyName,
          pharmacist_name: pharmacistName,
          pharmacist_license: pharmacistLicense,
          notes,
          items
        })
      });
      setResult(data);
    } catch (exception) {
      setError((exception as ApiError).message || "The prescription could not be dispensed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div className="public-shell">
        <header className="public-header">
          <Link href="/" className="brand">
            <BrandMark />
            <span>PharmaLink</span>
          </Link>
        </header>
        <main className="public-main narrow">
          <section className="panel">
            <Notice tone="success">
              Dispensed and recorded for {result.pharmacy_name}. The prescription is now{" "}
              <strong>{result.prescription_status.replace(/_/g, " ").toLowerCase()}</strong>.
            </Notice>
            <h2>Remaining on this prescription</h2>
            {result.remaining.every((item) => item.quantity_remaining === 0) ? (
              <p className="muted">Nothing left. Every item has been fully dispensed.</p>
            ) : (
              <ul className="clean-list">
                {result.remaining.map((item) => (
                  <li key={item.id}>
                    {item.medicine_text}: <strong>{item.quantity_remaining}</strong> still claimable at any pharmacy
                  </li>
                ))}
              </ul>
            )}
            <Link className="button" href="/rx">
              Dispense another prescription
            </Link>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link href="/" className="brand">
          <BrandMark />
          <span>PharmaLink</span>
        </Link>
        <Link className="button button-secondary" href="/rx">
          Different prescription
        </Link>
      </header>

      <main className="public-main narrow">
        {loading ? <div className="skeleton-card" /> : null}
        {error ? <Notice tone="danger">{error}</Notice> : null}

        {needsPin && !prescription ? (
          <section className="panel">
            <h1>Enter the prescription PIN</h1>
            <p className="muted">
              Prescription <strong>{code}</strong>. The 6-digit PIN is printed with the QR code in the
              patient&apos;s email.
            </p>
            <form
              className="stacked-form"
              onSubmit={(event) => {
                event.preventDefault();
                void lookup(pin);
              }}
            >
              <Field label="PIN">
                <input
                  value={pin}
                  onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  inputMode="numeric"
                  placeholder="000000"
                  autoFocus
                />
              </Field>
              <Button type="submit" disabled={pin.length < 4}>
                Open prescription
              </Button>
            </form>
          </section>
        ) : null}

        {prescription ? (
          <>
            <section className="panel">
              <div className="section-header">
                <div>
                  <h1>{prescription.code}</h1>
                  <p className="muted">
                    Patient <strong>{prescription.patient_name}</strong>
                    {prescription.patient_date_of_birth ? ` · born ${prescription.patient_date_of_birth}` : ""}
                  </p>
                </div>
                <Badge tone={statusTone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
              </div>

              <dl className="detail-grid">
                <div>
                  <dt>Prescriber</dt>
                  <dd>
                    Dr. {prescription.doctor.full_name}
                    <br />
                    <span className="muted small">
                      Licence {prescription.doctor.license_number}
                      {prescription.doctor.specialty ? ` · ${prescription.doctor.specialty}` : ""}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Issued</dt>
                  <dd>{new Date(prescription.issued_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Valid until</dt>
                  <dd>{new Date(prescription.valid_until).toLocaleString()}</dd>
                </div>
                {prescription.pharmacy ? (
                  <div>
                    <dt>Signed in as</dt>
                    <dd>{prescription.pharmacy.name}</dd>
                  </div>
                ) : null}
              </dl>

              {prescription.diagnosis_note ? <Notice>Doctor&apos;s note: {prescription.diagnosis_note}</Notice> : null}
              {!prescription.is_consumable ? (
                <Notice tone="danger">
                  This prescription cannot be dispensed ({prescription.status.replace(/_/g, " ").toLowerCase()}).
                </Notice>
              ) : null}
            </section>

            {prescription.dispense_history.length > 0 ? (
              <section className="panel">
                <h2>Already dispensed elsewhere</h2>
                <ul className="clean-list">
                  {prescription.dispense_history.map((entry, index) => (
                    <li key={index}>
                      <strong>{entry.pharmacy_name}</strong> · {entry.units} unit(s) ·{" "}
                      {new Date(entry.dispensed_at).toLocaleString()}
                    </li>
                  ))}
                </ul>
                <p className="muted small">
                  A prescription can be filled across several pharmacies. Only the remaining quantities below are
                  still claimable.
                </p>
              </section>
            ) : null}

            <section className="panel">
              <h2>Dispense</h2>
              <form onSubmit={submitDispense} className="stacked-form">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Instructions</th>
                      <th>Prescribed</th>
                      <th>Remaining</th>
                      <th>Dispensing now</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prescription.items.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.medicine_text}</strong>
                          {item.allow_generic_substitution ? (
                            <>
                              <br />
                              <span className="muted small">Generic substitution allowed</span>
                            </>
                          ) : (
                            <>
                              <br />
                              <span className="muted small">No substitution</span>
                            </>
                          )}
                        </td>
                        <td className="muted">{item.dosage_instructions || "—"}</td>
                        <td>
                          {item.quantity_prescribed} {item.unit}
                        </td>
                        <td>
                          <strong>{item.quantity_remaining}</strong>
                        </td>
                        <td>
                          <input
                            type="number"
                            min={0}
                            max={item.quantity_remaining}
                            value={quantities[item.id] ?? 0}
                            disabled={!prescription.is_consumable || item.quantity_remaining === 0}
                            onChange={(event) =>
                              setQuantities((current) => ({
                                ...current,
                                [item.id]: Math.max(0, Math.min(item.quantity_remaining, Number(event.target.value) || 0))
                              }))
                            }
                            className="qty-input"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="form-grid">
                  {prescription.pharmacy ? null : (
                    <Field label="Your pharmacy name" hint="Required so the dispense can be attributed.">
                      <input value={pharmacyName} onChange={(event) => setPharmacyName(event.target.value)} placeholder="Corner Pharmacy" />
                    </Field>
                  )}
                  <Field label="Dispensing pharmacist">
                    <input value={pharmacistName} onChange={(event) => setPharmacistName(event.target.value)} placeholder="Full name" />
                  </Field>
                  <Field label="Pharmacist licence (optional)">
                    <input value={pharmacistLicense} onChange={(event) => setPharmacistLicense(event.target.value)} />
                  </Field>
                  <Field label="Notes (optional)">
                    <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Substitution, partial fill reason..." />
                  </Field>
                </div>

                <Button type="submit" disabled={submitting || !prescription.is_consumable}>
                  {submitting ? "Recording..." : "Confirm dispense"}
                </Button>
                <p className="muted small">
                  Recording a dispense is final and cannot exceed the prescribed quantity. This session expires{" "}
                  {Math.round(prescription.ticket_expires_in_seconds / 60)} minutes after the prescription was opened.
                </p>
              </form>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

export default function PrescriptionPage() {
  return (
    <Suspense fallback={<div className="center-screen"><div className="skeleton-card" /></div>}>
      <PrescriptionView />
    </Suspense>
  );
}
