"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Prescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";
import { ChatPanel } from "@/components/messaging/ChatPanel";

function tone(status: string) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

export default function DoctorPrescriptionDetailPage() {
  const t = useTranslations();
  const { id } = useParams<{ id: string }>();
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    apiFetch<Prescription>(`/doctor/prescriptions/${id}/`)
      .then(setPrescription)
      .catch(() => setError(t("doctorPrescriptionDetail.notFound")));
  }

  useEffect(load, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function cancel() {
    if (!prescription) return;
    const reason = window.prompt(t("doctorPrescriptionDetail.cancelPrompt"));
    if (reason === null) return;
    setBusy(true);
    setError("");
    try {
      const updated = await apiFetch<Prescription>(`/doctor/prescriptions/${id}/cancel/`, {
        method: "POST",
        body: JSON.stringify({ reason })
      });
      setPrescription(updated);
    } catch (exception) {
      setError((exception as ApiError).message || t("doctorPrescriptionDetail.cancelFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!prescription) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  const canCancel = prescription.status === "ISSUED" || prescription.status === "PARTIALLY_DISPENSED";
  const totalPrescribed = prescription.items.reduce((sum, item) => sum + item.quantity_prescribed, 0);
  const totalDispensed = prescription.items.reduce((sum, item) => sum + item.quantity_dispensed, 0);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>
            {t("doctorPrescriptionDetail.prescriptionLabel")} <code>{prescription.code}</code>
          </h1>
          <p className="muted">
            {prescription.patient_name}
            {prescription.patient_email ? ` · ${prescription.patient_email}` : ""}
            {prescription.patient_phone ? ` · ${prescription.patient_phone}` : ""}
            {prescription.patient_fax ? ` · ${prescription.patient_fax}` : ""}
          </p>
          {prescription.renewed_from_code ? (
            <p className="muted small">{t("doctorPrescriptionDetail.renewalOf", { code: prescription.renewed_from_code })}</p>
          ) : null}
        </div>
        <div className="toolbar">
          <Badge tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
          <Link className="button button-secondary" href="/doctor/prescriptions">
            {t("doctorPrescriptionDetail.backToList")}
          </Link>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      {prescription.target_pharmacy_name ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>{t("doctorPrescriptionDetail.sentTo")}</h3>
              <p className="muted small">{prescription.target_pharmacy_name}</p>
            </div>
            <ChatPanel basePath="/doctor/prescriptions" orderFulfillmentId={prescription.id} />
          </div>
        </section>
      ) : null}

      {prescription.status === "CANCELLED" ? (
        <Notice tone="danger">
          {t("doctorPrescriptionDetail.cancelledAt", {
            when: prescription.cancelled_at ? new Date(prescription.cancelled_at).toLocaleString() : ""
          })}
          {prescription.cancellation_reason ? ` — ${prescription.cancellation_reason}` : ""}
        </Notice>
      ) : null}

      <section className="metrics-grid">
        <div className="metric-card">
          <span>{t("doctorPrescriptionDetail.unitsDispensed")}</span>
          <strong>
            {totalDispensed}/{totalPrescribed}
          </strong>
        </div>
        <div className="metric-card">
          <span>{t("doctorPrescriptionDetail.issued")}</span>
          <strong style={{ fontSize: "1.1rem" }}>{new Date(prescription.issued_at).toLocaleDateString()}</strong>
        </div>
        <div className="metric-card">
          <span>{t("doctorPrescriptionDetail.validUntil")}</span>
          <strong style={{ fontSize: "1.1rem" }}>{new Date(prescription.valid_until).toLocaleDateString()}</strong>
        </div>
        <div className="metric-card">
          <span>{t("doctorPrescriptionDetail.emailedToPatient")}</span>
          <strong style={{ fontSize: "1.1rem" }}>
            {prescription.email_sent_at ? t("doctorPrescriptionDetail.yes") : t("doctorPrescriptionDetail.no")}
          </strong>
        </div>
        {prescription.fax_sent_at ? (
          <div className="metric-card">
            <span>{t("doctorPrescriptionDetail.faxedToPatient")}</span>
            <strong style={{ fontSize: "1.1rem" }}>{t("doctorPrescriptionDetail.yes")}</strong>
          </div>
        ) : null}
      </section>

      {prescription.diagnosis_note ? (
        <section className="panel">
          <h3>{t("doctorPrescriptionDetail.noteForPharmacist")}</h3>
          <p>{prescription.diagnosis_note}</p>
        </section>
      ) : null}

      <section className="panel">
        <h3>{t("doctorPrescriptionDetail.items")}</h3>
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>{t("doctorPrescriptionDetail.medicine")}</th>
                <th>{t("doctorPrescriptionDetail.dosage")}</th>
                <th>{t("doctorPrescriptionDetail.prescribed")}</th>
                <th>{t("doctorPrescriptionDetail.dispensed")}</th>
                <th>{t("doctorPrescriptionDetail.remaining")}</th>
                <th>{t("doctorPrescriptionDetail.substitution")}</th>
              </tr>
            </thead>
            <tbody>
              {prescription.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.medicine_text}</td>
                  <td className="muted small">{item.dosage_instructions || "—"}</td>
                  <td>
                    {item.quantity_prescribed} {item.unit}
                  </td>
                  <td>{item.quantity_dispensed}</td>
                  <td>{item.quantity_remaining}</td>
                  <td className="muted small">
                    {item.allow_generic_substitution ? t("doctorPrescriptionDetail.allowed") : t("doctorPrescriptionDetail.notAllowed")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Table>
      </section>

      <section className="panel">
        <h3>{t("doctorPrescriptionDetail.dispenseHistory")}</h3>
        {prescription.dispenses.length === 0 ? (
          <p className="muted small">{t("doctorPrescriptionDetail.notDispensedYet")}</p>
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("doctorPrescriptionDetail.pharmacy")}</th>
                  <th>{t("doctorPrescriptionDetail.pharmacist")}</th>
                  <th>{t("doctorPrescriptionDetail.dispensedAt")}</th>
                  <th>{t("doctorPrescriptionDetail.items")}</th>
                </tr>
              </thead>
              <tbody>
                {prescription.dispenses.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.pharmacy_name}</td>
                    <td>{entry.pharmacist_name}</td>
                    <td className="muted small">{new Date(entry.dispensed_at).toLocaleString()}</td>
                    <td className="muted small">
                      {entry.items.map((line) => `${line.name} × ${line.quantity}`).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      {canCancel ? (
        <section className="panel">
          <h3>{t("doctorPrescriptionDetail.cancelSection")}</h3>
          <p className="muted small">{t("doctorPrescriptionDetail.cancelHint")}</p>
          <Button type="button" variant="danger" onClick={cancel} disabled={busy}>
            {busy ? t("doctorPrescriptionDetail.cancelling") : t("doctorPrescriptionDetail.cancelPrescription")}
          </Button>
        </section>
      ) : null}
    </>
  );
}
