"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, PrescriptionRenewalRequest, RenewalRequestStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function tone(status: RenewalRequestStatus) {
  if (status === "APPROVED") return "success" as const;
  if (status === "DENIED") return "danger" as const;
  return "warning" as const;
}

/** PrescribeIT's "Renew Rx": pharmacies ask here, a doctor approves (issues a fresh linked
 * prescription) or denies from this page. */
export default function DoctorRenewalRequestsPage() {
  const t = useTranslations();
  const [requests, setRequests] = useState<PrescriptionRenewalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<Paginated<PrescriptionRenewalRequest> | PrescriptionRenewalRequest[]>("/doctor/renewal-requests/")
      .then((payload) => setRequests(asList(payload)))
      .catch(() => setError(t("doctorRenewalRequests.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  async function respond(request: PrescriptionRenewalRequest, approve: boolean) {
    const response_note = approve ? "" : window.prompt(t("doctorRenewalRequests.denyReasonPrompt")) || "";
    setBusyId(request.id);
    setError("");
    try {
      await apiFetch(`/doctor/renewal-requests/${request.id}/respond/`, { method: "POST", body: JSON.stringify({ approve, response_note }) });
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("doctorRenewalRequests.respondFailed"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("doctorRenewalRequests.title")}</h1>
          <p className="muted">{t("doctorRenewalRequests.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && requests.length === 0 ? <EmptyState title={t("doctorRenewalRequests.empty")} /> : null}

      {requests.length > 0 ? (
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>{t("doctorRenewalRequests.prescription")}</th>
                <th>{t("doctorRenewalRequests.patient")}</th>
                <th>{t("doctorRenewalRequests.pharmacy")}</th>
                <th>{t("doctorRenewalRequests.note")}</th>
                <th>{t("doctorRenewalRequests.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>
                    <Link href={`/doctor/prescriptions/${request.prescription}`}>
                      <code>{request.prescription_code}</code>
                    </Link>
                    {request.new_prescription_code ? (
                      <>
                        <br />
                        <span className="muted small">{t("doctorRenewalRequests.issuedAs", { code: request.new_prescription_code })}</span>
                      </>
                    ) : null}
                  </td>
                  <td>{request.patient_name}</td>
                  <td>{request.pharmacy_name}</td>
                  <td className="muted small">{request.note || "—"}</td>
                  <td>
                    <Badge tone={tone(request.status)}>{request.status}</Badge>
                  </td>
                  <td>
                    {request.status === "PENDING" ? (
                      <div className="toolbar">
                        <Button type="button" variant="secondary" disabled={busyId === request.id} onClick={() => respond(request, true)}>
                          {t("doctorRenewalRequests.approve")}
                        </Button>
                        <Button type="button" variant="danger" disabled={busyId === request.id} onClick={() => respond(request, false)}>
                          {t("doctorRenewalRequests.deny")}
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Table>
      ) : null}
    </>
  );
}
