"use client";

import { Fragment, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE_URL, PRESCRIPTION_PREFILL_KEY } from "@/lib/constants";
import { apiFetch, asList, getToken } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { PrescriptionOcrResult, PrescriptionRecord } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
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
  const [extractions, setExtractions] = useState<Record<string, PrescriptionOcrResult>>({});
  const [extractingId, setExtractingId] = useState("");

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

  async function runExtract(record: PrescriptionRecord) {
    setError("");
    setExtractingId(record.id);
    try {
      const result = await apiFetch<PrescriptionOcrResult>(`/pharmacy/prescriptions/${record.id}/extract/`, { method: "POST" });
      setExtractions((prev) => ({ ...prev, [record.id]: result }));
    } catch {
      setError(t("pharmacyPrescriptions.extractFailed"));
    } finally {
      setExtractingId("");
    }
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
              <Fragment key={record.id}>
                <tr>
                  <td>{record.patient_name || t("pharmacyPrescriptions.notStored")}</td>
                  <td>{record.doctor_name || t("pharmacyPrescriptions.notRecorded")}</td>
                  <td>{record.prescription_date || new Date(record.created_at).toLocaleDateString()}</td>
                  <td>{record.file_name || t("pharmacyPrescriptions.noFile")}</td>
                  <td className="actions">
                    <Button type="button" variant="secondary" onClick={() => download(record)}>
                      {t("pharmacyPrescriptions.download")}
                    </Button>
                    <Button type="button" variant="secondary" disabled={extractingId === record.id} onClick={() => runExtract(record)}>
                      {extractingId === record.id ? t("pharmacyPrescriptions.extracting") : t("pharmacyPrescriptions.extractOcr")}
                    </Button>
                  </td>
                </tr>
                {extractions[record.id] ? (
                  <tr>
                    <td colSpan={5}>
                      <OcrPanel recordId={record.id} result={extractions[record.id]} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

function OcrPanel({ recordId, result }: { recordId: string; result: PrescriptionOcrResult }) {
  const t = useTranslations();
  const router = useRouter();
  const matchedIndexes = result.candidates.map((c, index) => index).filter((index) => result.candidates[index].medicine_id);
  const [selected, setSelected] = useState<Record<number, boolean>>(() => Object.fromEntries(matchedIndexes.map((index) => [index, true])));
  const [quantities, setQuantities] = useState<Record<number, number>>(() =>
    Object.fromEntries(result.candidates.map((c, index) => [index, c.quantity_guess ?? 1]))
  );
  const [warning, setWarning] = useState("");

  function useInNewSale() {
    const lines = result.candidates
      .map((candidate, index) => ({ candidate, index }))
      .filter(({ candidate, index }) => selected[index] && candidate.medicine_id)
      .map(({ candidate, index }) => ({
        medicine: candidate.medicine_id as string,
        quantity: quantities[index] || 1,
        unit_price: "",
        discount: "0"
      }));
    if (lines.length === 0) {
      setWarning(t("pharmacyPrescriptions.noLinesSelected"));
      return;
    }
    window.sessionStorage.setItem(PRESCRIPTION_PREFILL_KEY, JSON.stringify({ recordId, lines }));
    router.push("/pharmacy/sales/new");
  }

  return (
    <div className="panel">
      <div className="section-header">
        <h3>{t("pharmacyPrescriptions.ocrResultsTitle")}</h3>
        <Badge tone="neutral">{t("pharmacyPrescriptions.ocrProvider", { provider: result.provider })}</Badge>
      </div>
      <Notice>{t("pharmacyPrescriptions.ocrReviewNotice")}</Notice>
      {result.candidates.length === 0 ? (
        <EmptyState title={t("pharmacyPrescriptions.noCandidates")} />
      ) : (
        <>
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyPrescriptions.includeInSale")}</th>
                  <th>{t("pharmacyPrescriptions.candidateMatch")}</th>
                  <th>{t("pharmacyPrescriptions.candidateDosage")}</th>
                  <th>{t("pharmacyPrescriptions.candidateQuantity")}</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.map((candidate, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        type="checkbox"
                        disabled={!candidate.medicine_id}
                        checked={Boolean(selected[index])}
                        onChange={(event) => setSelected((prev) => ({ ...prev, [index]: event.target.checked }))}
                      />
                    </td>
                    <td>
                      {candidate.medicine_id ? (
                        <>
                          {candidate.medicine_name} <Badge tone="success">{Math.round(candidate.confidence * 100)}%</Badge>
                        </>
                      ) : (
                        <>
                          <span className="muted small">{candidate.raw_line}</span>{" "}
                          <Badge status tone="warning">{t("pharmacyPrescriptions.candidateNoMatch")}</Badge>
                        </>
                      )}
                    </td>
                    <td>{candidate.dosage_guess || "—"}</td>
                    <td>
                      <input
                        type="number"
                        min="1"
                        className="qty-input"
                        value={quantities[index] ?? 1}
                        disabled={!candidate.medicine_id}
                        onChange={(event) => setQuantities((prev) => ({ ...prev, [index]: Number(event.target.value) }))}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
          <div className="actions">
            <Button type="button" onClick={useInNewSale}>
              {t("pharmacyPrescriptions.useInNewSale")}
            </Button>
          </div>
          {warning ? <Notice tone="danger">{warning}</Notice> : null}
        </>
      )}
      <details className="explain">
        <summary>{t("pharmacyPrescriptions.ocrRawText")}</summary>
        <pre className="code-block">{result.ocr_text}</pre>
      </details>
    </div>
  );
}
