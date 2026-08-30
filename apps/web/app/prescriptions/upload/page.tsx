"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { PageHead } from "@/components/patient/Page";
import { FormAlert } from "@/components/site/FormField";
import { OcrReadout } from "@/components/prescriptions/OcrReadout";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { ApiError, apiFetch } from "@/lib/api-client";
import { toOcrFields } from "@/lib/patient/adapters";
import { usePrescriptionUploads } from "@/lib/patient/store";
import type { OcrFields } from "@/lib/patient/types";
import { blockingFindings, inspectScan, type ScanFinding } from "@/lib/prescription-scan-check";
import type { OcrFields as ApiOcrFields, PrescriptionUpload } from "@/types/api";

const MAX_MB = 10;
const ACCEPT = ".pdf,.jpg,.jpeg,.png";

/**
 * Upload a photo of a paper prescription.
 *
 * A quick in-browser legibility check runs on the picked image and nudges the
 * patient to retake a dark or blurry one before it is sent. It is only a nudge:
 * the server re-checks and is the authority, and a pharmacist reviews every
 * upload by hand before anything is dispensed against it.
 *
 * The prescriber, date and medications are read off the photo by OCR - the
 * patient does not type them. A pre-submit `preview` call shows that read on
 * this page so they see it before uploading; the server re-runs OCR on submit
 * (authoritative), and the read stays editable only by a pharmacist. If it is
 * wrong the patient flags it from the Prescriptions screen.
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
  const [reading, setReading] = useState(false);
  const [ocrPreview, setOcrPreview] = useState<OcrFields | null>(null);
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

  const readScan = useCallback(async (picked: File) => {
    setReading(true);
    try {
      const body = new FormData();
      body.set("file", picked);
      const res = await apiFetch<{ ocr_fields: ApiOcrFields | null }>("/shop/prescription-uploads/preview/", {
        method: "POST",
        body
      });
      setOcrPreview(toOcrFields(res.ocr_fields));
    } catch {
      // The preview is a convenience - if it fails, the upload still OCRs server-side.
      setOcrPreview(null);
    } finally {
      setReading(false);
    }
  }, []);

  const onPick = useCallback(
    async (picked: File | null) => {
      setError("");
      setFindings([]);
      setOcrPreview(null);
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
      void readScan(picked);
      setChecking(true);
      try {
        setFindings(await inspectScan(picked));
      } finally {
        setChecking(false);
      }
    },
    [readScan]
  );

  const blocked = blockingFindings(findings).length > 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || blocked || submitting) return;
    setSubmitting(true);
    setError("");

    const body = new FormData();
    body.set("file", file);
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
          lead="Photograph or scan a prescription a doctor gave you on paper. We read the details off it for you, and a pharmacy reviews it before anything is dispensed."
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

          {reading ? <p className="hc-small">Reading the prescription…</p> : null}
          <OcrReadout
            fields={ocrPreview}
            footnote="This is what we read from your photo. It goes to the pharmacy with the scan - if anything is wrong you can flag it once it is uploaded, and a pharmacist corrects it."
          />

          <div className="hc-field">
            <label htmlFor="rx-note">
              Note for the pharmacy<span className="hc-field-hint"> (optional)</span>
            </label>
            <input
              id="rx-note"
              className="hc-input"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Anything the pharmacist should know"
            />
          </div>

          {error ? <FormAlert tone="error">{error}</FormAlert> : null}

          <p className="hc-inline-note">
            <Icon name="lock" size={15} />
            Your prescription is encrypted and only shared with a pharmacy you order from.
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
