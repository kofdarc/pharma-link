"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import type { Prescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function tone(status: string) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

export default function DoctorPrescriptionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    apiFetch<Prescription>(`/doctor/prescriptions/${id}/`)
      .then(setPrescription)
      .catch(() => setError("Prescription not found, or it does not belong to you."));
  }

  useEffect(load, [id]);

  async function cancel() {
    if (!prescription) return;
    const reason = window.prompt("Reason for cancelling this prescription?");
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
      setError((exception as ApiError).message || "Could not cancel this prescription.");
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
            Prescription <code>{prescription.code}</code>
          </h1>
          <p className="muted">
            {prescription.patient_name}
            {prescription.patient_email ? ` · ${prescription.patient_email}` : ""}
            {prescription.patient_phone ? ` · ${prescription.patient_phone}` : ""}
          </p>
        </div>
        <div className="toolbar">
          <Badge tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
          <Link className="button button-secondary" href="/doctor/prescriptions">
            Back to list
          </Link>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      {prescription.status === "CANCELLED" ? (
        <Notice tone="danger">
          Cancelled {prescription.cancelled_at ? new Date(prescription.cancelled_at).toLocaleString() : ""}
          {prescription.cancellation_reason ? ` — ${prescription.cancellation_reason}` : ""}
        </Notice>
      ) : null}

      <section className="metrics-grid">
        <div className="metric-card">
          <span>Units dispensed</span>
          <strong>
            {totalDispensed}/{totalPrescribed}
          </strong>
        </div>
        <div className="metric-card">
          <span>Issued</span>
          <strong style={{ fontSize: "1.1rem" }}>{new Date(prescription.issued_at).toLocaleDateString()}</strong>
        </div>
        <div className="metric-card">
          <span>Valid until</span>
          <strong style={{ fontSize: "1.1rem" }}>{new Date(prescription.valid_until).toLocaleDateString()}</strong>
        </div>
        <div className="metric-card">
          <span>Emailed to patient</span>
          <strong style={{ fontSize: "1.1rem" }}>{prescription.email_sent_at ? "Yes" : "No"}</strong>
        </div>
      </section>

      {prescription.diagnosis_note ? (
        <section className="panel">
          <h3>Note for the pharmacist</h3>
          <p>{prescription.diagnosis_note}</p>
        </section>
      ) : null}

      <section className="panel">
        <h3>Items</h3>
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>Medicine</th>
                <th>Dosage</th>
                <th>Prescribed</th>
                <th>Dispensed</th>
                <th>Remaining</th>
                <th>Substitution</th>
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
                  <td className="muted small">{item.allow_generic_substitution ? "Allowed" : "Not allowed"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Table>
      </section>

      <section className="panel">
        <h3>Dispense history</h3>
        {prescription.dispenses.length === 0 ? (
          <p className="muted small">Not dispensed at any pharmacy yet.</p>
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Pharmacy</th>
                  <th>Pharmacist</th>
                  <th>Dispensed at</th>
                  <th>Items</th>
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
          <h3>Cancel this prescription</h3>
          <p className="muted small">
            Once cancelled, no pharmacy will be able to dispense it, even partially. This cannot be undone.
          </p>
          <Button type="button" variant="danger" onClick={cancel} disabled={busy}>
            {busy ? "Cancelling..." : "Cancel prescription"}
          </Button>
        </section>
      ) : null}
    </>
  );
}
