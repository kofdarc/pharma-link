"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { PageHead } from "@/components/patient/Page";
import { FormAlert } from "@/components/site/FormField";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { ApiError, apiFetch } from "@/lib/api-client";
import { usePrescriptionUploads } from "@/lib/patient/store";
import { blockingFindings, inspectScan, type ScanFinding } from "@/lib/prescription-scan-check";
import type { PrescriptionUpload } from "@/types/api";

const MAX_MB = 10;
const ACCEPT = ".pdf,.jpg,.jpeg,.png";

/**
 * Upload a photo of a paper prescription.
 *
 * A quick in-browser legibility check runs on the picked image and nudges the
 * patient to retake a dark or blurry one before it is sent. It is only a nudge:
 * the server re-checks and is the authority, and a pharmacist reviews every
 * upload by hand before anything is dispensed against it.
 */
export default function UploadPrescriptionPage() {
  const router = useRouter();
  const { notify } = useToast();
  const { refresh } = usePrescriptionUploads();
  const formRef = useRef<HTMLFormElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [findings, setFindings] = useState<ScanFinding[]>([]);
  const [checking, setChecking] = useState(false);
  const [doctorName, setDoctorName] = useState("");
  const [prescriptionDate, setPrescriptionDate] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const onPick = useCallback(async (picked: File | null) => {
    setError("");
    setFindings([]);
    if (!picked) {
      setFile(null);
      return;
    }
    if (picked.size > MAX_MB * 1024 * 1024) {
      setFile(null);
      setError(`That file is over ${MAX_MB} MB. Try a photo instead of a scan, or a lower resolution.`);
      return;
    }
    setFile(picked);
    setChecking(true);
    try {
      setFindings(await inspectScan(picked));
    } finally {
      setChecking(false);
    }
  }, []);

  const blocked = blockingFindings(findings).length > 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || blocked || submitting) return;
    setSubmitting(true);
    setError("");

    const body = new FormData();
    body.set("file", file);
    if (doctorName.trim()) body.set("doctor_name", doctorName.trim());
    if (prescriptionDate) body.set("prescription_date", prescriptionDate);
    if (note.trim()) body.set("notes", note.trim());

    try {
      const created = await apiFetch<PrescriptionUpload>("/shop/prescription-uploads/", { method: "POST", body });
      refresh();
      const advice = created.quality_warnings?.[0];
      notify(advice ? `Prescription uploaded. ${advice}` : "Prescription uploaded for review");
      router.push("/prescriptions");
    } catch (exception) {
      const api = exception as ApiError;
      const detail = api.details as { file?: string } | undefined;
      setError(detail?.file || api.message || "Could not upload that prescription.");
      setSubmitting(false);
    }
  }

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <PageHead
          title="Upload a paper prescription"
          lead="Photograph or scan a prescription a doctor gave you on paper. A pharmacy reviews it before anything is dispensed."
          back={{ href: "/prescriptions", label: "Prescriptions" }}
        />

        <form ref={formRef} className="hc-card hc-form" onSubmit={submit}>
          <div className="hc-field">
            <label htmlFor="rx-file">Prescription photo or scan</label>
            <input
              id="rx-file"
              className="hc-input"
              type="file"
              accept={ACCEPT}
              required
              onChange={(event) => onPick(event.target.files?.[0] ?? null)}
            />
            <p className="hc-field-hint">PDF, JPG or PNG, up to {MAX_MB} MB. Fit the whole page in frame, in good light.</p>
          </div>

          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- local object-URL preview, not a remote asset
            <img
              src={previewUrl}
              alt="Preview of the prescription you selected"
              style={{ maxWidth: "260px", maxHeight: "340px", borderRadius: "10px", border: "1px solid var(--hc-line, rgba(0,0,0,0.12))" }}
            />
          ) : null}

          {checking ? <p className="hc-small">Checking the photo…</p> : null}

          {findings.map((finding) => (
            <FormAlert key={finding.code} tone={finding.severity === "block" ? "error" : "info"}>
              {finding.message}
            </FormAlert>
          ))}
          {blocked ? <p className="hc-small">Choose or take another photo to continue.</p> : null}

          <div className="hc-form-row">
            <div className="hc-field">
              <label htmlFor="rx-doctor">
                Prescribing doctor<span className="hc-field-hint"> (optional)</span>
              </label>
              <input id="rx-doctor" className="hc-input" value={doctorName} onChange={(event) => setDoctorName(event.target.value)} placeholder="Dr. …" />
            </div>
            <div className="hc-field">
              <label htmlFor="rx-date">
                Date on the prescription<span className="hc-field-hint"> (optional)</span>
              </label>
              <input id="rx-date" className="hc-input" type="date" value={prescriptionDate} onChange={(event) => setPrescriptionDate(event.target.value)} />
            </div>
          </div>

          <div className="hc-field">
            <label htmlFor="rx-note">
              Note for the pharmacy<span className="hc-field-hint"> (optional)</span>
            </label>
            <input id="rx-note" className="hc-input" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Anything the pharmacist should know" />
          </div>

          {error ? <FormAlert tone="error">{error}</FormAlert> : null}

          <p className="hc-inline-note">
            <Icon name="lock" size={15} />
            Your prescription is encrypted at rest and only shared with a pharmacy you order from.
          </p>

          <div className="hc-actions">
            <button type="submit" className="hc-btn hc-btn-primary hc-btn-lg" disabled={!file || blocked || checking || submitting}>
              {submitting ? "Uploading…" : "Upload prescription"}
            </button>
            <Link href="/prescriptions" className="hc-btn hc-btn-secondary hc-btn-lg">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </PatientShell>
  );
}
