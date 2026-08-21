"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
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
  const t = useTranslations();
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
      setError(t("doctorPrescriptionsNew.addItemFailed"));
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
      setError((exception as ApiError).message || t("doctorPrescriptionsNew.issueFailed"));
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
            <h1>{t("doctorPrescriptionsNew.issuedTitle", { code: issued.code })}</h1>
            <p className="muted">
              {issued.email_sent_at
                ? t("doctorPrescriptionsNew.emailedTo", { email: issued.patient_email || "" })
                : t("doctorPrescriptionsNew.noEmailGiven")}
            </p>
          </div>
          <div className="toolbar no-print">
            <Button type="button" variant="secondary" onClick={() => window.print()}>
              {t("doctorPrescriptionsNew.print")}
            </Button>
            <Link className="button button-secondary" href="/doctor/prescriptions">
              {t("doctorPrescriptionsNew.backToList")}
            </Link>
          </div>
        </div>

        <Notice tone="danger">
          <span className="no-print">{t("doctorPrescriptionsNew.secretShownOnceNotice")}</span>
        </Notice>

        <div className="panel rx-issued">
          {secrets ? (
            <>
              <div className="rx-qr" dangerouslySetInnerHTML={{ __html: secrets.qr_svg }} />
              <div>
                <h3>{t("doctorPrescriptionsNew.patientHandOff")}</h3>
                <p>
                  {t("doctorPrescriptionsNew.code")}: <code className="big-code">{issued.code}</code>
                </p>
                <p>
                  {t("doctorPrescriptionsNew.pin")}: <code className="big-code">{secrets.pin}</code>
                </p>
                <p className="muted small">{t("doctorPrescriptionsNew.anyPharmacyHint")}</p>
                <p className="muted small">
                  {t("doctorPrescriptionsNew.validUntil", { when: new Date(issued.valid_until).toLocaleString() })}
                </p>
              </div>
            </>
          ) : null}
        </div>

        <div className="panel">
          <h3>{t("doctorPrescriptionsNew.prescribed")}</h3>
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
          <h1>{t("doctorPrescriptionsNew.title")}</h1>
          <p className="muted">{t("doctorPrescriptionsNew.subtitle")}</p>
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
          <h3>{t("doctorPrescriptionsNew.patient")}</h3>
          <div className="form-grid">
            <Field
              label={t("doctorPrescriptionsNew.fullName")}
              hint={knownPatients.length > 0 ? t("doctorPrescriptionsNew.returningPatientHint") : undefined}
            >
              <input list="known-patients" value={patientName} onChange={(event) => selectPatientName(event.target.value)} required />
            </Field>
            <Field label={t("doctorPrescriptionsNew.email")} hint={t("doctorPrescriptionsNew.emailHint")}>
              <input type="email" value={patientEmail} onChange={(event) => setPatientEmail(event.target.value)} />
            </Field>
            <Field label={t("doctorPrescriptionsNew.phone")}>
              <input value={patientPhone} onChange={(event) => setPatientPhone(event.target.value)} />
            </Field>
            <Field label={t("doctorPrescriptionsNew.validForDays")}>
              <input
                type="number"
                min={1}
                max={365}
                value={validityDays}
                onChange={(event) => setValidityDays(Number(event.target.value) || 30)}
              />
            </Field>
          </div>
          <Field label={t("doctorPrescriptionsNew.noteForPharmacist")}>
            <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Complete the full course" />
          </Field>
        </section>

        <section className="panel">
          <div className="section-header">
            <h3>{t("doctorPrescriptionsNew.items")}</h3>
            <Button type="button" variant="secondary" onClick={() => setItems((current) => [...current, emptyItem()])}>
              {t("doctorPrescriptionsNew.addItem")}
            </Button>
          </div>

          {items.map((item, index) => (
            <div key={item.key} className="rx-item-row">
              <div className="form-grid">
                <Field
                  label={t("doctorPrescriptionsNew.itemFromCatalog", { index: index + 1 })}
                  hint={t("doctorPrescriptionsNew.typeToSearch")}
                >
                  <input
                    list="medicine-catalog"
                    value={item.catalog_query}
                    onChange={(event) => selectCatalogEntry(item.key, event.target.value)}
                    placeholder="Start typing a medicine name"
                  />
                </Field>
                <Field label={t("doctorPrescriptionsNew.orWriteIt")} hint={t("doctorPrescriptionsNew.keptVerbatimHint")}>
                  <input
                    value={item.medicine_text}
                    onChange={(event) => update(item.key, { medicine_text: event.target.value })}
                    placeholder="e.g. Augmentin 1g"
                  />
                </Field>
                <Field label={t("doctorPrescriptionsNew.quantity")}>
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={item.quantity_prescribed}
                    onChange={(event) => update(item.key, { quantity_prescribed: Number(event.target.value) || 1 })}
                  />
                </Field>
                <Field label={t("doctorPrescriptionsNew.unit")}>
                  <input value={item.unit} onChange={(event) => update(item.key, { unit: event.target.value })} />
                </Field>
              </div>
              <div className="form-grid">
                <Field label={t("doctorPrescriptionsNew.dosageInstructions")}>
                  <input
                    value={item.dosage_instructions}
                    onChange={(event) => update(item.key, { dosage_instructions: event.target.value })}
                    placeholder="1 tablet twice daily for 7 days"
                  />
                </Field>
                <div className="field">
                  <span>&nbsp;</span>
                  <label className="checkbox-field">
                    <span>{t("doctorPrescriptionsNew.genericSubstitution")}</span>
                    <input
                      type="checkbox"
                      checked={item.allow_generic_substitution}
                      onChange={(event) => update(item.key, { allow_generic_substitution: event.target.checked })}
                    />
                    <small>{t("doctorPrescriptionsNew.allowSubstitutionHint")}</small>
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
                      {t("doctorPrescriptionsNew.removeItem")}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </section>

        <Button type="submit" disabled={busy}>
          {busy ? t("doctorPrescriptionsNew.issuing") : t("doctorPrescriptionsNew.issueAndEmail")}
        </Button>
      </form>
    </>
  );
}
