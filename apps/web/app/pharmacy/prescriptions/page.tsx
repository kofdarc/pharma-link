"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/constants";
import { apiFetch, asList, getToken } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { PrescriptionRecord } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function PrescriptionsPage() {
  const t = useTranslations();
  const [records, setRecords] = useState<PrescriptionRecord[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<PrescriptionRecord[] | { results: PrescriptionRecord[] }>("/pharmacy/prescriptions/")
      .then((payload) => setRecords(asList(payload)))
      .catch(() => setError(t("pharmacyPrescriptions.loadError")));
  }

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<PrescriptionRecord>("/pharmacy/prescriptions/", { method: "POST", body: form });
      setMessage(t("pharmacyPrescriptions.uploaded"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("pharmacyPrescriptions.uploadFailed"));
    }
  }

  async function download(record: PrescriptionRecord) {
    if (!record.download_url) return;
    const response = await fetch(`${API_BASE_URL}${record.download_url.replace("/api", "")}`, {
      headers: { Authorization: `Token ${getToken()}` }
    });
    if (!response.ok) {
      setError(t("pharmacyPrescriptions.downloadFailed"));
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
          <h1>{t("pharmacyPrescriptions.title")}</h1>
          <p>{t("pharmacyPrescriptions.subtitle")}</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={upload}>
        <Field label={t("pharmacyPrescriptions.patientName")}>
          <input name="patient_name" />
        </Field>
        <Field label={t("pharmacyPrescriptions.doctorName")}>
          <input name="doctor_name" />
        </Field>
        <Field label={t("pharmacyPrescriptions.prescriptionDate")}>
          <input type="date" name="prescription_date" />
        </Field>
        <Field label={t("pharmacyPrescriptions.file")}>
          <input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png" required />
        </Field>
        <Button type="submit">{t("pharmacyPrescriptions.uploadPrescription")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {records.length === 0 ? <EmptyState title={t("pharmacyPrescriptions.noPrescriptions")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacyPrescriptions.patient")}</th>
              <th>{t("pharmacyPrescriptions.doctor")}</th>
              <th>{t("pharmacyPrescriptions.date")}</th>
              <th>{t("pharmacyPrescriptions.file")}</th>
              <th>{t("pharmacyPrescriptions.action")}</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.patient_name || t("pharmacyPrescriptions.notStored")}</td>
                <td>{record.doctor_name || t("pharmacyPrescriptions.notRecorded")}</td>
                <td>{record.prescription_date || new Date(record.created_at).toLocaleDateString()}</td>
                <td>{record.file_name || t("pharmacyPrescriptions.noFile")}</td>
                <td>
                  <Button type="button" variant="secondary" onClick={() => download(record)}>
                    {t("pharmacyPrescriptions.download")}
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

