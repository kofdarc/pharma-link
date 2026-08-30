"use client";

import { useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { OcrReadout } from "@/components/prescriptions/OcrReadout";
import { getToken } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/constants";
import { formatDate } from "@/lib/patient/format";
import type { PrescriptionUpload, PrescriptionUploadStatus } from "@/lib/patient/types";

/**
 * Paper prescriptions the patient uploaded, each waiting on a pharmacy.
 *
 * Sits above the digital wallet on the Prescriptions screen and only appears
 * once there is something in it: an empty account should not carry an empty
 * section explaining a feature it has not used.
 *
 * Each card shows what OCR read off the photo, read-only. The patient cannot
 * edit it - if something is wrong they flag it and the pharmacy corrects it on
 * review.
 */

const STATUS: Record<PrescriptionUploadStatus, { label: string; chip: string; icon: IconName }> = {
  pending: { label: "Pending review", chip: "hc-chip-limited", icon: "clock" },
  accepted: { label: "Accepted", chip: "hc-chip-ok", icon: "check" },
  rejected: { label: "Rejected", chip: "hc-chip-off", icon: "close" }
};

export function UploadedPrescriptions({
  uploads,
  ready,
  onRemove,
  onFlag
}: {
  uploads: PrescriptionUpload[];
  ready: boolean;
  onRemove: (id: string) => void;
  onFlag: (id: string, note: string) => void;
}) {
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [flagId, setFlagId] = useState("");
  const [flagNote, setFlagNote] = useState("");

  if (!ready || uploads.length === 0) return null;

  async function view(upload: PrescriptionUpload) {
    if (!upload.filePath) return;
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}${upload.filePath}`, {
        headers: { Authorization: `Token ${getToken()}` }
      });
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setError("Could not open that file. Try again in a moment.");
    }
  }

  async function remove(id: string) {
    setBusyId(id);
    try {
      await onRemove(id);
    } finally {
      setBusyId("");
    }
  }

  async function submitFlag(id: string) {
    setBusyId(id);
    try {
      await onFlag(id, flagNote.trim());
      setFlagId("");
      setFlagNote("");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="hc-stack" aria-label="Uploaded prescriptions">
      <h2 className="hc-h3">Uploaded prescriptions</h2>
      <p className="hc-small">Photos you sent in. A pharmacy checks each one before it can be used to dispense.</p>

      {error ? (
        <p className="hc-field-error">
          <Icon name="alert" size={14} />
          {error}
        </p>
      ) : null}

      {uploads.map((upload) => {
        const status = STATUS[upload.status];
        return (
          <article className="hc-card" key={upload.id}>
            <div className="hc-card-head">
              <div>
                <p className="hc-card-label">{formatDate(upload.uploadedOn)}</p>
                <h3 className="hc-h3">{upload.fileName || "Prescription scan"}</h3>
                {upload.doctorName ? <p className="hc-small">{upload.doctorName}</p> : null}
              </div>
              <span className={`hc-chip hc-status ${status.chip}`}>
                <Icon name={status.icon} size={13} strokeWidth={2.1} />
                {status.label}
              </span>
            </div>

            {upload.status === "rejected" && upload.rejectionReason ? (
              <p className="hc-inline-note hc-inline-note-warn">
                <Icon name="info" size={15} />
                {upload.rejectionReason}
              </p>
            ) : null}

            {upload.status === "pending" && upload.qualityWarnings.length > 0 ? (
              <p className="hc-small">{upload.qualityWarnings.join(" ")}</p>
            ) : null}

            <OcrReadout fields={upload.ocrFields} />

            {upload.status === "pending" ? (
              upload.ocrReviewRequested ? (
                <p className="hc-inline-note hc-inline-note-warn">
                  <Icon name="info" size={15} />
                  You flagged these details. A pharmacist will re-check them against your photo.
                </p>
              ) : flagId === upload.id ? (
                <div className="hc-field">
                  <label htmlFor={`flag-${upload.id}`}>What did we get wrong?</label>
                  <input
                    id={`flag-${upload.id}`}
                    className="hc-input"
                    value={flagNote}
                    onChange={(event) => setFlagNote(event.target.value)}
                    placeholder="e.g. the doctor's name, or a missing medication"
                  />
                  <div className="hc-rxcard-actions">
                    <button
                      type="button"
                      className="hc-btn hc-btn-primary hc-btn-sm"
                      disabled={busyId === upload.id}
                      onClick={() => submitFlag(upload.id)}
                    >
                      Send to pharmacy
                    </button>
                    <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={() => setFlagId("")}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null
            ) : null}

            <div className="hc-rxcard-actions">
              {upload.filePath ? (
                <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={() => view(upload)}>
                  View file
                </button>
              ) : null}
              {upload.status === "pending" && !upload.ocrReviewRequested && flagId !== upload.id ? (
                <button
                  type="button"
                  className="hc-btn hc-btn-secondary hc-btn-sm"
                  onClick={() => {
                    setFlagId(upload.id);
                    setFlagNote("");
                  }}
                >
                  <Icon name="alert" size={14} />
                  Something look wrong?
                </button>
              ) : null}
              {upload.status === "pending" ? (
                <button
                  type="button"
                  className="hc-btn hc-btn-secondary hc-btn-sm"
                  disabled={busyId === upload.id}
                  onClick={() => remove(upload.id)}
                >
                  <Icon name="trash" size={14} />
                  Remove
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}
