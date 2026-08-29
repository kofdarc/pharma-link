"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, asList } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/constants";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, Prescription, PrescriptionStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

function tone(status: string) {
  if (status === "FULLY_DISPENSED") return "success" as const;
  if (status === "PARTIALLY_DISPENSED") return "warning" as const;
  if (status === "CANCELLED" || status === "EXPIRED") return "danger" as const;
  return "info" as const;
}

export default function DoctorPrescriptionsPage() {
  const t = useTranslations();
  const STATUS_OPTIONS: { value: PrescriptionStatus | ""; label: string }[] = [
    { value: "", label: t("doctorPrescriptions.allStatuses") },
    { value: "ISSUED", label: t("doctorPrescriptions.issued") },
    { value: "PARTIALLY_DISPENSED", label: t("doctorPrescriptions.partiallyDispensed") },
    { value: "FULLY_DISPENSED", label: t("doctorPrescriptions.fullyDispensed") },
    { value: "EXPIRED", label: t("doctorPrescriptions.expired") },
    { value: "CANCELLED", label: t("doctorPrescriptions.cancelled") }
  ];
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [count, setCount] = useState(0);
  const [nextPath, setNextPath] = useState<string | null>(null);
  const [prevPath, setPrevPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [patientQuery, setPatientQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<PrescriptionStatus | "">("");

  const fetchPage = useCallback((path: string) => {
    setLoading(true);
    apiFetch<Paginated<Prescription> | Prescription[]>(path)
      .then((payload) => {
        if (Array.isArray(payload)) {
          setPrescriptions(payload);
          setCount(payload.length);
          setNextPath(null);
          setPrevPath(null);
        } else {
          setPrescriptions(payload.results);
          setCount(payload.count);
          setNextPath(payload.next ? payload.next.replace(API_BASE_URL, "") : null);
          setPrevPath(payload.previous ? payload.previous.replace(API_BASE_URL, "") : null);
        }
      })
      .catch(() => setError(t("doctorPrescriptions.loadError")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (patientQuery.trim()) params.set("patient", patientQuery.trim());
    if (statusFilter) params.set("status", statusFilter);
    const query = params.toString();
    const timeout = setTimeout(() => fetchPage(`/doctor/prescriptions/${query ? `?${query}` : ""}`), 300);
    return () => clearTimeout(timeout);
  }, [patientQuery, statusFilter, fetchPage]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("doctorPrescriptions.title")}</h1>
          <p className="muted">{t("doctorPrescriptions.subtitle")}</p>
        </div>
        <LinkButton href="/doctor/prescriptions/new" variant="primary">
          {t("doctorPrescriptions.writeAPrescription")}
        </LinkButton>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <section className="panel">
        <div className="search-bar">
          <Field label={t("doctorPrescriptions.patient")}>
            <input
              value={patientQuery}
              onChange={(event) => setPatientQuery(event.target.value)}
              placeholder={t("doctorPrescriptions.searchByPatientName")}
            />
          </Field>
          <Field label={t("doctorPrescriptions.status")}>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as PrescriptionStatus | "")}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </section>

      {loading ? <div className="skeleton-card" /> : null}

      {!loading && prescriptions.length === 0 ? (
        <EmptyState
          title={t("doctorPrescriptions.noMatch")}
          detail={
            patientQuery || statusFilter
              ? t("doctorPrescriptions.tryDifferentSearch")
              : t("doctorPrescriptions.writeFirstOne")
          }
        />
      ) : null}

      {prescriptions.length > 0 ? (
        <div className="panel">
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("doctorPrescriptions.code")}</th>
                  <th>{t("doctorPrescriptions.patient")}</th>
                  <th>{t("doctorPrescriptions.items")}</th>
                  <th>{t("doctorPrescriptions.dispensedAt")}</th>
                  <th>{t("doctorPrescriptions.issuedCol")}</th>
                  <th>{t("doctorPrescriptions.validUntil")}</th>
                  <th>{t("doctorPrescriptions.status")}</th>
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
                        {t("doctorPrescriptions.itemsCount", { count: prescription.items.length })}
                        <br />
                        <span className="muted small">
                          {t("doctorPrescriptions.unitsDispensed", { dispensed: totalDispensed, prescribed: totalPrescribed })}
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
                        <Badge status tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Table>

          {nextPath || prevPath ? (
            <div className="section-header">
              <span className="muted small">
                {t("doctorPrescriptions.ofCount", { shown: prescriptions.length, count })}
              </span>
              <div className="toolbar">
                <Button type="button" variant="secondary" disabled={!prevPath} onClick={() => prevPath && fetchPage(prevPath)}>
                  {t("doctorPrescriptions.previous")}
                </Button>
                <Button type="button" variant="secondary" disabled={!nextPath} onClick={() => nextPath && fetchPage(nextPath)}>
                  {t("doctorPrescriptions.next")}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
