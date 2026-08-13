"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { Medicine, Paginated, Prescription } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

interface DraftItem {
  key: string;
  medicine: string;
  medicine_text: string;
  quantity_prescribed: number;
  unit: string;
  dosage_instructions: string;
  allow_generic_substitution: boolean;
}

function emptyItem(): DraftItem {
  return {
    key: Math.random().toString(36).slice(2),
    medicine: "",
    medicine_text: "",
    quantity_prescribed: 1,
    unit: "tablet",
    dosage_instructions: "",
    allow_generic_substitution: true
  };
}

export default function NewPrescriptionPage() {
  const [catalog, setCatalog] = useState<Medicine[]>([]);
  const [patientName, setPatientName] = useState("");
  const [patientEmail, setPatientEmail] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [validityDays, setValidityDays] = useState(30);
  const [note, setNote] = useState("");
  const [items, setItems] = useState<DraftItem[]>([emptyItem()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<Prescription | null>(null);

  useEffect(() => {
    apiFetch<Paginated<Medicine> | Medicine[]>("/medicines/")
      .then((payload) => setCatalog(asList(payload)))
      .catch(() => setCatalog([]));
  }, []);

  function update(key: string, patch: Partial<DraftItem>) {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const payloadItems = items
      .filter((item) => item.medicine || item.medicine_text.trim())
      .map((item) => ({
        medicine: item.medicine || null,
        medicine_text: item.medicine_text || catalog.find((entry) => entry.id === item.medicine)?.display_name || "",
        quantity_prescribed: item.quantity_prescribed,
        unit: item.unit,
        dosage_instructions: item.dosage_instructions,
        allow_generic_substitution: item.allow_generic_substitution
      }));

    if (payloadItems.length === 0) {
      setError("Add at least one item.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await apiFetch<Prescription>("/doctor/prescriptions/", {
        method: "POST",
        body: JSON.stringify({
          patient_name: patientName,
          patient_email: patientEmail,
          patient_phone: patientPhone,
          diagnosis_note: note,
          validity_days: validityDays,
          items: payloadItems
        })
      });
      setIssued(result);
    } catch (exception) {
      setError((exception as ApiError).message || "Could not issue the prescription.");
    } finally {
      setBusy(false);
    }
  }

  if (issued) {
    const secrets = issued.one_time_secrets;
    return (
      <>
        <div className="section-header">
          <div>
            <h1>Prescription {issued.code} issued</h1>
            <p className="muted">
              {issued.email_sent_at
                ? `Emailed to ${issued.patient_email} with the QR code attached.`
                : "No patient email was given, so share the code and PIN below directly."}
            </p>
          </div>
          <Link className="button button-secondary" href="/doctor/prescriptions">
            Back to list
          </Link>
        </div>

        <Notice tone="danger">
          The PIN and QR link below are shown <strong>once</strong>. They are not stored in recoverable form and
          cannot be displayed again. If they are lost, cancel this prescription and issue a new one.
        </Notice>

        <div className="panel rx-issued">
          {secrets ? (
            <>
              <div className="rx-qr" dangerouslySetInnerHTML={{ __html: secrets.qr_svg }} />
              <div>
                <h3>Patient hand-off</h3>
                <p>
                  Code: <code className="big-code">{issued.code}</code>
                </p>
                <p>
                  PIN: <code className="big-code">{secrets.pin}</code>
                </p>
                <p className="muted small">
                  Any pharmacy can scan the QR, or open <strong>/rx</strong> and type the code and PIN. No account
                  is needed on their side.
                </p>
                <p className="muted small">Valid until {new Date(issued.valid_until).toLocaleString()}</p>
              </div>
            </>
          ) : null}
        </div>

        <div className="panel">
          <h3>Prescribed</h3>
          <ul className="clean-list">
            {issued.items.map((item) => (
              <li key={item.id}>
                <strong>{item.medicine_text}</strong> — {item.quantity_prescribed} {item.unit}
                {item.dosage_instructions ? ` · ${item.dosage_instructions}` : ""}
              </li>
            ))}
          </ul>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Write a prescription</h1>
          <p className="muted">
            The patient receives a secure QR code by email. Any pharmacy can dispense it, in full or in part.
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <form onSubmit={submit}>
        <section className="panel">
          <h3>Patient</h3>
          <div className="form-grid">
            <Field label="Full name">
              <input value={patientName} onChange={(event) => setPatientName(event.target.value)} required />
            </Field>
            <Field label="Email" hint="Where the QR code is sent. Leave blank to hand over the code in person.">
              <input type="email" value={patientEmail} onChange={(event) => setPatientEmail(event.target.value)} />
            </Field>
            <Field label="Phone">
              <input value={patientPhone} onChange={(event) => setPatientPhone(event.target.value)} />
            </Field>
            <Field label="Valid for (days)">
              <input
                type="number"
                min={1}
                max={365}
                value={validityDays}
                onChange={(event) => setValidityDays(Number(event.target.value) || 30)}
              />
            </Field>
          </div>
          <Field label="Note for the pharmacist (optional)">
            <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Complete the full course" />
          </Field>
        </section>

        <section className="panel">
          <div className="section-header">
            <h3>Items</h3>
            <Button type="button" variant="secondary" onClick={() => setItems((current) => [...current, emptyItem()])}>
              Add item
            </Button>
          </div>

          {items.map((item, index) => (
            <div key={item.key} className="rx-item-row">
              <div className="form-grid">
                <Field label={`Item ${index + 1} — from catalog`}>
                  <select
                    value={item.medicine}
                    onChange={(event) => {
                      const selected = catalog.find((entry) => entry.id === event.target.value);
                      update(item.key, {
                        medicine: event.target.value,
                        medicine_text: selected?.display_name || item.medicine_text
                      });
                    }}
                  >
                    <option value="">Not in catalog — type it below</option>
                    {catalog.map((medicine) => (
                      <option key={medicine.id} value={medicine.id}>
                        {medicine.display_name}
                        {medicine.requires_prescription ? " (Rx)" : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Or write it" hint="Kept verbatim for the pharmacist.">
                  <input
                    value={item.medicine_text}
                    onChange={(event) => update(item.key, { medicine_text: event.target.value })}
                    placeholder="e.g. Augmentin 1g"
                  />
                </Field>
                <Field label="Quantity">
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={item.quantity_prescribed}
                    onChange={(event) => update(item.key, { quantity_prescribed: Number(event.target.value) || 1 })}
                  />
                </Field>
                <Field label="Unit">
                  <input value={item.unit} onChange={(event) => update(item.key, { unit: event.target.value })} />
                </Field>
              </div>
              <div className="form-grid">
                <Field label="Dosage instructions">
                  <input
                    value={item.dosage_instructions}
                    onChange={(event) => update(item.key, { dosage_instructions: event.target.value })}
                    placeholder="1 tablet twice daily for 7 days"
                  />
                </Field>
                <label className="field checkbox-field">
                  <span>Generic substitution</span>
                  <input
                    type="checkbox"
                    checked={item.allow_generic_substitution}
                    onChange={(event) => update(item.key, { allow_generic_substitution: event.target.checked })}
                  />
                  <small>Allow the pharmacy to substitute an equivalent generic.</small>
                </label>
                {items.length > 1 ? (
                  <Button
                    type="button"
                    variant="danger"
                    onClick={() => setItems((current) => current.filter((entry) => entry.key !== item.key))}
                  >
                    Remove item
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </section>

        <Button type="submit" disabled={busy}>
          {busy ? "Issuing..." : "Issue and email the prescription"}
        </Button>
      </form>
    </>
  );
}
