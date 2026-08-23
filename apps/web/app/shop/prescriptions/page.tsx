"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Prescription, PrescriptionStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

function prescriptionTone(status: PrescriptionStatus) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

export default function ShopPrescriptionsPage() {
  const t = useTranslations();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    apiFetch<Prescription[]>("/shop/prescriptions/mine/")
      .then(setPrescriptions)
      .catch((exception) => setError((exception as ApiError).message || t("myPrescriptions.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("myPrescriptions.title")}</h1>
          <p className="muted">{t("myPrescriptions.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && prescriptions.length === 0 ? (
        <EmptyState title={t("myPrescriptions.noPrescriptions")} detail={t("myPrescriptions.noPrescriptionsHint")} />
      ) : null}

      {prescriptions.map((prescription) => (
        <section className="panel" key={prescription.id}>
          <div className="section-header">
            <div>
              <h3>{prescription.code}</h3>
              <p className="muted small">
                {t("myPrescriptions.prescriber", { doctor: prescription.doctor_name, license: prescription.doctor_license })}
              </p>
            </div>
            <Badge tone={prescriptionTone(prescription.status)}>{t(`myPrescriptions.status.${prescription.status}`)}</Badge>
          </div>

          <dl className="detail-grid">
            <div>
              <dt>{t("myPrescriptions.issued")}</dt>
              <dd>{new Date(prescription.issued_at).toLocaleDateString()}</dd>
            </div>
            <div>
              <dt>{t("myPrescriptions.validUntil")}</dt>
              <dd>{new Date(prescription.valid_until).toLocaleDateString()}</dd>
            </div>
          </dl>

          {prescription.diagnosis_note ? <Notice>{prescription.diagnosis_note}</Notice> : null}

          <table className="table">
            <thead>
              <tr>
                <th>{t("myPrescriptions.item")}</th>
                <th>{t("myPrescriptions.prescribed")}</th>
                <th>{t("myPrescriptions.dispensed")}</th>
                <th>{t("myPrescriptions.remaining")}</th>
              </tr>
            </thead>
            <tbody>
              {prescription.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.medicine_detail?.display_name || item.medicine_text}</strong>
                    {item.dosage_instructions ? (
                      <>
                        <br />
                        <span className="muted small">{item.dosage_instructions}</span>
                      </>
                    ) : null}
                  </td>
                  <td>
                    {item.quantity_prescribed} {item.unit}
                  </td>
                  <td>{item.quantity_dispensed}</td>
                  <td>
                    <strong>{item.quantity_remaining}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {prescription.dispenses.length > 0 ? (
            <>
              <h4>{t("myPrescriptions.dispenseHistory")}</h4>
              <ul className="clean-list">
                {prescription.dispenses.map((dispense) => (
                  <li key={dispense.id}>
                    <strong>{dispense.pharmacy_name}</strong> · {new Date(dispense.dispensed_at).toLocaleString()} ·{" "}
                    {dispense.items.map((line) => `${line.quantity} × ${line.name}`).join(", ")}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted small">{t("myPrescriptions.noDispenses")}</p>
          )}
        </section>
      ))}

      <Notice>
        {t("myPrescriptions.footerNoticeBefore")} <Link href="/shop/refills">{t("myPrescriptions.refillsLink")}</Link>.
      </Notice>
    </>
  );
}
