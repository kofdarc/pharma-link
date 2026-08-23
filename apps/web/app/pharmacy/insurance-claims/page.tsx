"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InsuranceClaim, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function claimTone(status: InsuranceClaim["status"]) {
  if (status === "PAID") return "success" as const;
  if (status === "REJECTED") return "danger" as const;
  if (status === "APPROVED") return "info" as const;
  if (status === "CANCELLED") return "neutral" as const;
  return "warning" as const;
}

export default function PharmacyInsuranceClaimsPage() {
  const t = useTranslations();
  const [claims, setClaims] = useState<InsuranceClaim[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    apiFetch<Paginated<InsuranceClaim> | InsuranceClaim[]>("/pharmacy/insurance-claims/")
      .then((payload) => setClaims(asList(payload)))
      .catch(() => setError(t("pharmacyInsuranceClaims.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  async function act(claim: InsuranceClaim, status: "APPROVED" | "REJECTED" | "PAID") {
    setError("");
    let approval_code = "";
    let rejection_reason = "";
    if (status === "APPROVED") approval_code = window.prompt(t("pharmacyInsuranceClaims.approvalCodePrompt")) || "";
    if (status === "REJECTED") rejection_reason = window.prompt(t("pharmacyInsuranceClaims.rejectionReasonPrompt")) || "";
    try {
      await apiFetch(`/pharmacy/insurance-claims/${claim.id}/status/`, {
        method: "POST",
        body: JSON.stringify({ status, approval_code, rejection_reason })
      });
      setMessage(`${claim.policy_detail.holder_name} — ${status}`);
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyInsuranceClaims.actionFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyInsuranceClaims.title")}</h1>
          <p className="muted">{t("pharmacyInsuranceClaims.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {claims.length === 0 ? (
        <EmptyState title={t("pharmacyInsuranceClaims.noClaims")} />
      ) : (
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>{t("pharmacyInsuranceClaims.source")}</th>
                <th>{t("pharmacyInsuranceClaims.patient")}</th>
                <th>{t("pharmacyInsuranceClaims.billed")}</th>
                <th>{t("pharmacyInsuranceClaims.covered")}</th>
                <th>{t("pharmacyInsuranceClaims.copay")}</th>
                <th>{t("pharmacyInsuranceClaims.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {claims.map((claim) => (
                <tr key={claim.id}>
                  <td>{claim.order_reference || claim.invoice_number}</td>
                  <td>
                    {claim.policy_detail.holder_name}
                    <br />
                    <span className="muted small">{claim.policy_detail.plan_detail.provider_name}</span>
                  </td>
                  <td>${claim.billed_amount}</td>
                  <td>${claim.covered_amount}</td>
                  <td>${claim.patient_copay}</td>
                  <td>
                    <Badge tone={claimTone(claim.status)}>{claim.status}</Badge>
                  </td>
                  <td>
                    {claim.status === "SUBMITTED" ? (
                      <>
                        <Button type="button" variant="secondary" onClick={() => act(claim, "APPROVED")}>
                          {t("pharmacyInsuranceClaims.approve")}
                        </Button>{" "}
                        <Button type="button" variant="secondary" onClick={() => act(claim, "REJECTED")}>
                          {t("pharmacyInsuranceClaims.reject")}
                        </Button>
                      </>
                    ) : null}
                    {claim.status === "APPROVED" ? (
                      <Button type="button" variant="secondary" onClick={() => act(claim, "PAID")}>
                        {t("pharmacyInsuranceClaims.markPaid")}
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Table>
      )}
    </>
  );
}
