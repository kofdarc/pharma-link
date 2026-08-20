"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { groupPatients, type Patient } from "@/lib/patients";
import { takeDraft } from "@/lib/rxDraft";
import type { Medicine, Paginated, Prescription } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

interface DraftItem {
  key: string;
  medicine: string;
  medicine_text: string;
  catalog_query: string;
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
    catalog_query: "",
    quantity_prescribed: 1,
    unit: "tablet",
    dosage_instructions: "",
    allow_generic_substitution: true
  };
}

function catalogLabel(medicine: Medicine) {
  return medicine.requires_prescription ? `${medicine.display_name} (Rx)` : medicine.display_name;
}

export default function NewPrescriptionPage() {
  const [catalog, setCatalog] = useState<Medicine[]>([]);
  const [knownPatients, setKnownPatients] = useState<Patient[]>([]);
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

  useEffect(() => {
    apiFetch<Paginated<Prescription> | Prescription[]>("/doctor/prescriptions/")
      .then((payload) => setKnownPatients(groupPatients(asList(payload))))
      .catch(() => setKnownPatients([]));
  }, []);

  useEffect(() => {
    const draft = takeDraft();
    if (!draft) return;
    setPatientName(draft.patient_name);
    setPatientEmail(draft.patient_email);
    setPatientPhone(draft.patient_phone);
    setItems(
      draft.items.length
        ? draft.items.map((entry) => ({
            key: Math.random().toString(36).slice(2),
            medicine: entry.medicine,
            medicine_text: entry.medicine_text,
            catalog_query: "",
            quantity_prescribed: entry.quantity_prescribed,
            unit: entry.unit,
            dosage_instructions: entry.dosage_instructions,
            allow_generic_substitution: entry.allow_generic_substitution
          }))
        : [emptyItem()]
    );
  }, []);

  // Draft items only carry a catalog id, not its display label - backfill the search
  // box's text once the catalog has loaded, whichever effect finishes first.
  useEffect(() => {
    if (catalog.length === 0) return;
    setItems((current) =>
      current.map((item) => {
        if (!item.medicine || item.catalog_query) return item;
        const match = catalog.find((entry) => entry.id === item.medicine);
        return match ? { ...item, catalog_query: catalogLabel(match) } : item;
      })
    );
  }, [catalog]);

  const isDirty = useMemo(
    () =>
      !issued &&
      (patientName.trim() !== "" ||
        patientEmail.trim() !== "" ||
        patientPhone.trim() !== "" ||
        note.trim() !== "" ||
        items.some((item) => item.medicine_text.trim() !== "" || item.catalog_query.trim() !== "" || item.dosage_instructions.trim() !== "")),
    [issued, patientName, patientEmail, patientPhone, note, items]
  );

  useEffect(() => {
    function handler(event: BeforeUnloadEvent) {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  function update(key: string, patch: Partial<DraftItem>) {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  function selectPatientName(value: string) {
    setPatientName(value);
    const match = knownPatients.find((patient) => patient.name.toLowerCase() === value.trim().toLowerCase());
    if (!match) return;
    if (!patientEmail.trim() && match.email) setPatientEmail(match.email);
    if (!patientPhone.trim() && match.phone) setPatientPhone(match.phone);
  }

  function selectCatalogEntry(key: string, value: string) {
    const selected = catalog.find((entry) => catalogLabel(entry) === value);
    update(key, {
      catalog_query: value,
      medicine: selected ? selected.id : "",
      medicine_text: selected ? selected.display_name : items.find((item) => item.key === key)?.medicine_text || ""
    });
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
          <div className="toolbar no-print">
            <Button type="button" variant="secondary" onClick={() => window.print()}>
              Print
            </Button>
            <Link className="button button-secondary" href="/doctor/prescriptions">
              Back to list
            </Link>
          </div>
        </div>

        <Notice tone="danger">
          <span className="no-print">
            The PIN and QR link below are shown <strong>once</strong>. They are not stored in recoverable form and
            cannot be displayed again. If they are lost, cancel this prescription and issue a new one.
          </span>
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

      <datalist id="known-patients">
        {knownPatients.map((patient) => (
          <option key={patient.key} value={patient.name} />
        ))}
      </datalist>
      <datalist id="medicine-catalog">
        {catalog.map((medicine) => (
          <option key={medicine.id} value={catalogLabel(medicine)} />
        ))}
      </datalist>

      <form onSubmit={submit}>
        <section className="panel">
          <h3>Patient</h3>
          <div className="form-grid">
            <Field label="Full name" hint={knownPatients.length > 0 ? "Type a returning patient's name to reuse their contact details." : undefined}>
              <input list="known-patients" value={patientName} onChange={(event) => selectPatientName(event.target.value)} required />
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
                <Field label={`Item ${index + 1} — from catalog`} hint="Type to search.">
                  <input
                    list="medicine-catalog"
                    value={item.catalog_query}
                    onChange={(event) => selectCatalogEntry(item.key, event.target.value)}
                    placeholder="Start typing a medicine name"
                  />
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
                <div className="field">
                  <span>&nbsp;</span>
                  <label className="checkbox-field">
                    <span>Generic substitution</span>
                    <input
                      type="checkbox"
                      checked={item.allow_generic_substitution}
                      onChange={(event) => update(item.key, { allow_generic_substitution: event.target.checked })}
                    />
                    <small>Allow the pharmacy to substitute an equivalent generic.</small>
                  </label>
                </div>
                {items.length > 1 ? (
                  <div className="field">
                    <span>&nbsp;</span>
                    <Button
                      type="button"
                      variant="danger"
                      onClick={() => setItems((current) => current.filter((entry) => entry.key !== item.key))}
                    >
                      Remove item
                    </Button>
                  </div>
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
