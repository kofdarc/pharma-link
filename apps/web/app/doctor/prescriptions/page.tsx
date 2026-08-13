"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, asList } from "@/lib/api-client";
import type { Paginated, Prescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function tone(status: string) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

export default function DoctorPrescriptionsPage() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Paginated<Prescription> | Prescription[]>("/doctor/prescriptions/")
      .then((payload) => setPrescriptions(asList(payload)))
      .catch(() => setError("Could not load your prescriptions."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Prescriptions you have issued</h1>
          <p className="muted">
            Each one was emailed to the patient as a QR code. Any pharmacy can consume it, including pharmacies
            with no PharmaLink account.
          </p>
        </div>
        <LinkButton href="/doctor/prescriptions/new" variant="primary">
          Write a prescription
        </LinkButton>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}

      {!loading && prescriptions.length === 0 ? (
        <EmptyState title="No prescriptions yet." detail="Write your first one and it will be emailed to the patient straight away." />
      ) : null}

      {prescriptions.length > 0 ? (
        <div className="panel">
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Patient</th>
                  <th>Items</th>
                  <th>Dispensed at</th>
                  <th>Issued</th>
                  <th>Valid until</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {prescriptions.map((prescription) => {
                  const totalPrescribed = prescription.items.reduce((sum, item) => sum + item.quantity_prescribed, 0);
                  const totalDispensed = prescription.items.reduce((sum, item) => sum + item.quantity_dispensed, 0);
                  return (
                    <tr key={prescription.id}>
                      <td>
                        <Link href={`/doctor/prescriptions/${prescription.id}`}>
                          <code>{prescription.code}</code>
                        </Link>
                      </td>
                      <td>{prescription.patient_name}</td>
                      <td>
                        {prescription.items.length} item(s)
                        <br />
                        <span className="muted small">
                          {totalDispensed}/{totalPrescribed} units dispensed
                        </span>
                      </td>
                      <td className="muted small">
                        {prescription.dispenses.length === 0
                          ? "—"
                          : prescription.dispenses.map((entry) => entry.pharmacy_name).join(", ")}
                      </td>
                      <td className="muted small">{new Date(prescription.issued_at).toLocaleDateString()}</td>
                      <td className="muted small">{new Date(prescription.valid_until).toLocaleDateString()}</td>
                      <td>
                        <Badge tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Table>
        </div>
      ) : null}
    </>
  );
}
