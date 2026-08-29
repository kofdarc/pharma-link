"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { PharmacyApplication } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function tone(status: PharmacyApplication["status"]) {
  if (status === "APPROVED") return "success" as const;
  if (status === "REJECTED") return "danger" as const;
  return "warning" as const;
}

export default function PharmacyApplicationsPage() {
  const [applications, setApplications] = useState<PharmacyApplication[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    apiFetch<{ results: PharmacyApplication[] } | PharmacyApplication[]>("/admin/pharmacy-applications/")
      .then((payload) => setApplications(asList(payload)))
      .catch(() => setError("Could not load pharmacy applications."));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function approve(application: PharmacyApplication) {
    setError("");
    try {
      await apiFetch(`/admin/pharmacy-applications/${application.id}/approve/`, { method: "POST" });
      setMessage(`${application.pharmacy_name} approved. An invite email was sent to ${application.email}.`);
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  async function reject(application: PharmacyApplication) {
    const note = window.prompt(`Reason for rejecting ${application.pharmacy_name}? (optional)`) || "";
    setError("");
    try {
      await apiFetch(`/admin/pharmacy-applications/${application.id}/reject/`, { method: "POST", body: JSON.stringify({ note }) });
      setMessage(`${application.pharmacy_name} rejected.`);
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  const pending = applications.filter((application) => application.status === "PENDING");
  const reviewed = applications.filter((application) => application.status !== "PENDING");

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Pharmacy applications</h1>
          <p className="muted">Requests from prospective pharmacies to join the platform.</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      <section className="panel">
        <h3>Pending review</h3>
        {pending.length === 0 ? (
          <EmptyState title="Nothing waiting on review." />
        ) : (
          pending.map((application) => (
            <div className="allocation-card" key={application.id}>
              <div className="section-header">
                <div>
                  <strong>{application.pharmacy_name}</strong>
                  <p className="muted small">
                    {application.owner_name} · {application.email} · {application.phone}
                    {application.area ? ` · ${application.area}, ${application.city}` : ""}
                  </p>
                  {application.message ? <p className="muted small">&ldquo;{application.message}&rdquo;</p> : null}
                </div>
                <div className="actions">
                  <Button type="button" onClick={() => approve(application)}>
                    Approve
                  </Button>
                  <Button type="button" variant="danger" onClick={() => reject(application)}>
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </section>

      <section className="panel">
        <h3>Reviewed</h3>
        {reviewed.length === 0 ? (
          <EmptyState title="No applications reviewed yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Pharmacy</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {reviewed.map((application) => (
                  <tr key={application.id}>
                    <td>{application.pharmacy_name}</td>
                    <td>{application.email}</td>
                    <td>
                      <Badge status tone={tone(application.status)}>{application.status}</Badge>
                    </td>
                    <td className="muted small">{application.review_note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>
    </>
  );
}
