"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/constants";
import { apiFetch, asList, getToken } from "@/lib/api-client";
import type { PrescriptionRecord } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function PrescriptionsPage() {
  const [records, setRecords] = useState<PrescriptionRecord[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<PrescriptionRecord[] | { results: PrescriptionRecord[] }>("/pharmacy/prescriptions/")
      .then((payload) => setRecords(asList(payload)))
      .catch(() => setError("Prescriptions failed to load."));
  }

  useEffect(load, []);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<PrescriptionRecord>("/pharmacy/prescriptions/", { method: "POST", body: form });
      setMessage("Prescription record uploaded.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Upload failed. Use PDF, JPG, JPEG, or PNG within the configured size limit.");
    }
  }

  async function download(record: PrescriptionRecord) {
    if (!record.download_url) return;
    const response = await fetch(`${API_BASE_URL}${record.download_url.replace("/api", "")}`, {
      headers: { Authorization: `Token ${getToken()}` }
    });
    if (!response.ok) {
      setError("Download failed or unauthorized.");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = record.file_name || "prescription";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Prescriptions</h1>
          <p>Prescription files are private and downloaded only through authenticated API routes.</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={upload}>
        <Field label="Patient name">
          <input name="patient_name" />
        </Field>
        <Field label="Doctor name">
          <input name="doctor_name" />
        </Field>
        <Field label="Prescription date">
          <input type="date" name="prescription_date" />
        </Field>
        <Field label="File">
          <input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png" required />
        </Field>
        <Button type="submit">Upload prescription</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {records.length === 0 ? <EmptyState title="No prescriptions stored yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Patient</th>
              <th>Doctor</th>
              <th>Date</th>
              <th>File</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.patient_name || "Not stored"}</td>
                <td>{record.doctor_name || "Not recorded"}</td>
                <td>{record.prescription_date || new Date(record.created_at).toLocaleDateString()}</td>
                <td>{record.file_name || "No file"}</td>
                <td>
                  <Button type="button" variant="secondary" onClick={() => download(record)}>
                    Download
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

