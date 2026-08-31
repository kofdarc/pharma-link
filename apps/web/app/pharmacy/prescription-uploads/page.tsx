"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiFetch, asList, getToken } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/constants";
import type { OcrMedication, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

/**
 * The pharmacy's queue of patient paper-prescription uploads.
 *
 * OCR has already read the scan into structured fields on upload. The pharmacist
 * corrects that read inline - it is not a binary accept-as-is / reject - then
 * accepts or rejects. Editing an unclaimed upload claims it for this pharmacy.
 */

interface OcrFields {
  patient_name: string;
  patient_phone: string;
  doctor_name: string;
  prescription_date: string;
  medications: OcrMedication[];
  notes: string;
}

interface Upload {
  id: string;
  status: "PENDING_REVIEW" | "ACCEPTED" | "REJECTED";
  customer_email: string;
  patient_name: string;
  patient_phone: string;
  doctor_name: string;
  prescription_date: string | null;
  notes: string;
  rejection_reason: string;
  ocr_fields: OcrFields;
  ocr_provider: string;
  ocr_review_requested: boolean;
  ocr_review_note: string;
  quality_warnings: string[];
  file_name: string;
  download_url: string | null;
  created_at: string;
}

const EMPTY_MED: OcrMedication = {
  name: "",
  strength: "",
  quantity: null,
  dose_pattern: "",
  directions: "",
  duration: "",
  refills: null,
  medicine_id: "",
  catalog_name: "",
  match_confidence: 0
};

function statusTone(status: Upload["status"]) {
  if (status === "ACCEPTED") return "success" as const;
  if (status === "REJECTED") return "danger" as const;
  return "info" as const;
}

export default function PharmacyPrescriptionUploadsPage() {
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [draft, setDraft] = useState<OcrFields | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<Paginated<Upload> | Upload[]>("/pharmacy/prescription-uploads/")
      .then((payload) => setUploads(asList(payload)))
      .catch((exception) => setError((exception as ApiError).message || "Could not load uploads."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const open = useMemo(() => uploads.find((upload) => upload.id === openId) ?? null, [uploads, openId]);

  function toggle(upload: Upload) {
    if (openId === upload.id) {
      setOpenId(null);
      setDraft(null);
      return;
    }
    setOpenId(upload.id);
    setError("");
    setMessage("");
    setDraft({
      patient_name: upload.ocr_fields?.patient_name ?? upload.patient_name ?? "",
      patient_phone: upload.ocr_fields?.patient_phone ?? upload.patient_phone ?? "",
      doctor_name: upload.ocr_fields?.doctor_name ?? upload.doctor_name ?? "",
      prescription_date: upload.ocr_fields?.prescription_date ?? upload.prescription_date ?? "",
      medications: (upload.ocr_fields?.medications ?? []).map((med) => ({ ...EMPTY_MED, ...med })),
      notes: upload.ocr_fields?.notes ?? ""
    });
  }

  function patchMed(index: number, patch: Partial<OcrMedication>) {
    setDraft((current) =>
      current
        ? { ...current, medications: current.medications.map((med, i) => (i === index ? { ...med, ...patch } : med)) }
        : current
    );
  }

  async function viewScan(upload: Upload) {
    if (!upload.download_url) return;
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}${upload.download_url.replace(/^\/api/, "")}`, {
        headers: { Authorization: `Token ${getToken()}` }
      });
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setError("Could not open that scan.");
    }
  }

  async function run(label: string, request: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await request();
      setMessage(label);
      setOpenId(null);
      setDraft(null);
      load();
    } catch (exception) {
      setError((exception as ApiError).message || "That did not go through.");
    } finally {
      setBusy(false);
    }
  }

  function save(upload: Upload) {
    if (!draft) return;
    const cleanedMeds = draft.medications
      .filter((med) => med.name.trim())
      .map((med) => ({
        ...med,
        quantity: med.quantity === null || Number.isNaN(med.quantity) ? null : Number(med.quantity),
        refills: med.refills === null || Number.isNaN(med.refills) ? null : Number(med.refills)
      }));
    run("Corrections saved.", () =>
      apiFetch(`/pharmacy/prescription-uploads/${upload.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          ocr_fields: { ...draft, medications: cleanedMeds },
          patient_name: draft.patient_name,
          patient_phone: draft.patient_phone,
          doctor_name: draft.doctor_name,
          prescription_date: draft.prescription_date || null
        })
      })
    );
  }

  function accept(upload: Upload) {
    run(`Accepted ${upload.file_name || "upload"}.`, () =>
      apiFetch(`/pharmacy/prescription-uploads/${upload.id}/accept/`, { method: "POST" })
    );
  }

  function reject(upload: Upload) {
    const reason = window.prompt("Why are you rejecting this upload? The patient sees this.") || "";
    if (!reason.trim()) return;
    run(`Rejected ${upload.file_name || "upload"}.`, () =>
      apiFetch(`/pharmacy/prescription-uploads/${upload.id}/reject/`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() })
      })
    );
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Patient uploads</h1>
          <p className="muted">
            Photos of paper prescriptions patients sent in. OCR has read each one - check it against the scan, fix anything
            wrong, then accept or reject.
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && uploads.length === 0 ? (
        <EmptyState title="Nothing waiting" detail="Patient prescription uploads land here for review." />
      ) : null}

      {uploads.map((upload) => (
        <section key={upload.id} className="panel">
          <div className="section-header">
            <div>
              <h3>{upload.file_name || "Prescription scan"}</h3>
              <p className="muted small">
                {[upload.ocr_fields?.patient_name || upload.patient_name, upload.customer_email].filter(Boolean).join(" · ")}
                {upload.doctor_name ? ` · ${upload.doctor_name}` : ""}
                {upload.prescription_date ? ` · ${new Date(upload.prescription_date).toLocaleDateString()}` : ""}
              </p>
            </div>
            <div className="toolbar">
              <Badge status tone={statusTone(upload.status)}>
                {upload.status.replace(/_/g, " ")}
              </Badge>
              {upload.ocr_provider ? <span className="muted small">read by {upload.ocr_provider}</span> : null}
            </div>
          </div>

          {upload.ocr_review_requested ? (
            <Notice tone="info">
              The patient flagged this OCR read as wrong.
              {upload.ocr_review_note ? ` They said: "${upload.ocr_review_note}"` : ""}
            </Notice>
          ) : null}

          {upload.status === "REJECTED" && upload.rejection_reason ? (
            <Notice tone="danger">Rejected: {upload.rejection_reason}</Notice>
          ) : null}
          {upload.quality_warnings.length > 0 ? <p className="muted small">{upload.quality_warnings.join(" ")}</p> : null}

          <div className="toolbar">
            {upload.download_url ? (
              <Button type="button" variant="secondary" onClick={() => viewScan(upload)}>
                View scan
              </Button>
            ) : null}
            <Button type="button" variant="secondary" onClick={() => toggle(upload)}>
              {openId === upload.id ? "Close" : "Review"}
            </Button>
          </div>

          {openId === upload.id && draft ? (
            <div className="stacked-form">
              <div className="form-grid">
                <Field label="Patient name">
                  <input
                    value={draft.patient_name}
                    onChange={(event) => setDraft({ ...draft, patient_name: event.target.value })}
                  />
                </Field>
                <Field label="Patient phone">
                  <input
                    value={draft.patient_phone}
                    onChange={(event) => setDraft({ ...draft, patient_phone: event.target.value })}
                  />
                </Field>
                <Field label="Prescriber">
                  <input
                    value={draft.doctor_name}
                    onChange={(event) => setDraft({ ...draft, doctor_name: event.target.value })}
                  />
                </Field>
                <Field label="Date on prescription">
                  <input
                    type="date"
                    value={draft.prescription_date}
                    onChange={(event) => setDraft({ ...draft, prescription_date: event.target.value })}
                  />
                </Field>
              </div>

              <h4>Medications</h4>
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Strength</th>
                    <th>Qty</th>
                    <th>Directions</th>
                    <th>Duration</th>
                    <th>Refills</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {draft.medications.map((med, index) => (
                    <tr key={index}>
                      <td>
                        <input value={med.name} onChange={(event) => patchMed(index, { name: event.target.value })} />
                        {med.medicine_id ? (
                          <span className="med-match med-match-ok">In catalog: {med.catalog_name}</span>
                        ) : (
                          <span className="med-match med-match-none">Not matched to catalog - re-checks on save</span>
                        )}
                      </td>
                      <td>
                        <input
                          value={med.strength}
                          onChange={(event) => patchMed(index, { strength: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="qty-input"
                          type="number"
                          min={0}
                          value={med.quantity ?? ""}
                          onChange={(event) =>
                            patchMed(index, { quantity: event.target.value === "" ? null : Number(event.target.value) })
                          }
                        />
                      </td>
                      <td>
                        <input
                          value={med.directions}
                          onChange={(event) => patchMed(index, { directions: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          value={med.duration}
                          onChange={(event) => patchMed(index, { duration: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="qty-input"
                          type="number"
                          min={0}
                          value={med.refills ?? ""}
                          onChange={(event) =>
                            patchMed(index, { refills: event.target.value === "" ? null : Number(event.target.value) })
                          }
                        />
                      </td>
                      <td>
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() =>
                            setDraft({ ...draft, medications: draft.medications.filter((_, i) => i !== index) })
                          }
                        >
                          Remove
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setDraft({ ...draft, medications: [...draft.medications, { ...EMPTY_MED }] })}
              >
                Add a medication
              </Button>

              <Field label="Notes">
                <input value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />
              </Field>

              <div className="toolbar">
                <Button type="button" disabled={busy} onClick={() => save(upload)}>
                  {busy ? "Saving…" : "Save corrections"}
                </Button>
                <Button type="button" variant="secondary" disabled={busy} onClick={() => accept(upload)}>
                  Accept
                </Button>
                <Button type="button" variant="secondary" disabled={busy} onClick={() => reject(upload)}>
                  Reject
                </Button>
              </div>
            </div>
          ) : null}
        </section>
      ))}
    </>
  );
}
