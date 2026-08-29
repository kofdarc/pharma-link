"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { groupPatients } from "@/lib/patients";
import { draftFromPrescription, saveDraft } from "@/lib/rxDraft";
import type { Paginated, Prescription } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
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

export default function DoctorPatientsPage() {
  const t = useTranslations();
  const router = useRouter();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Paginated<Prescription> | Prescription[]>("/doctor/prescriptions/")
      .then((payload) => setPrescriptions(asList(payload)))
      .catch(() => setError(t("doctorPatients.loadError")))
      .finally(() => setLoading(false));
  }, []);

  const patients = useMemo(() => groupPatients(prescriptions), [prescriptions]);

  const filtered = useMemo(() => {
    if (!query.trim()) return patients;
    const needle = query.trim().toLowerCase();
    return patients.filter(
      (patient) =>
        patient.name.toLowerCase().includes(needle) ||
        patient.email.toLowerCase().includes(needle) ||
        patient.phone.toLowerCase().includes(needle)
    );
  }, [patients, query]);

  const selected = patients.find((patient) => patient.key === selectedKey) || null;

  function prescribeAgain(prescription: Prescription) {
    saveDraft(draftFromPrescription(prescription));
    router.push("/doctor/prescriptions/new");
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("doctorPatients.title")}</h1>
          <p className="muted">{t("doctorPatients.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}

      {!loading ? (
        <section className="panel">
          <div className="search-bar">
            <Field label={t("doctorPatients.search")}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("doctorPatients.searchPlaceholder")} />
            </Field>
          </div>

          {filtered.length === 0 ? (
            <EmptyState title={t("doctorPatients.noPatients")} detail={t("doctorPatients.noPatientsHint")} />
          ) : (
            <Table>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("doctorPatients.patient")}</th>
                    <th>{t("doctorPatients.contact")}</th>
                    <th>{t("doctorPatients.prescriptions")}</th>
                    <th>{t("doctorPatients.lastIssued")}</th>
                    <th>{t("doctorPatients.lastStatus")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((patient) => (
                    <tr key={patient.key}>
                      <td>
                        <strong>{patient.name}</strong>
                      </td>
                      <td className="muted small">
                        {patient.email || "—"}
                        {patient.phone ? <br /> : null}
                        {patient.phone || null}
                      </td>
                      <td>{patient.prescriptions.length}</td>
                      <td className="muted small">{new Date(patient.prescriptions[0].issued_at).toLocaleDateString()}</td>
                      <td>
                        <Badge status tone={tone(patient.prescriptions[0].status)}>{patient.prescriptions[0].status.replace(/_/g, " ")}</Badge>
                      </td>
                      <td>
                        <Button type="button" variant="secondary" onClick={() => setSelectedKey(patient.key)}>
                          {t("doctorPatients.open")}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Table>
          )}
        </section>
      ) : null}

      {selected ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>{selected.name}</h2>
              <p className="muted small">
                {selected.email || t("doctorPatients.noEmailOnFile")}
                {selected.phone ? ` · ${selected.phone}` : ""}
              </p>
            </div>
            <div className="toolbar">
              <Button type="button" variant="primary" onClick={() => prescribeAgain(selected.prescriptions[0])}>
                {t("doctorPatients.prescribeAgain")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setSelectedKey(null)}>
                {t("doctorPatients.close")}
              </Button>
            </div>
          </div>

          <ul className="clean-list">
            {selected.prescriptions.map((prescription) => (
              <li key={prescription.id} className="rx-item-row">
                <div className="section-header">
                  <div>
                    <Link href={`/doctor/prescriptions/${prescription.id}`}>
                      <code>{prescription.code}</code>
                    </Link>{" "}
                    <span className="muted small">
                      {t("doctorPatients.issuedValidUntil", {
                        issued: new Date(prescription.issued_at).toLocaleDateString(),
                        until: new Date(prescription.valid_until).toLocaleDateString()
                      })}
                    </span>
                  </div>
                  <div className="toolbar">
                    <Badge status tone={tone(prescription.status)}>{prescription.status.replace(/_/g, " ")}</Badge>
                    <Button type="button" variant="secondary" onClick={() => prescribeAgain(prescription)}>
                      {t("doctorPatients.prescribeAgain")}
                    </Button>
                  </div>
                </div>
                {prescription.diagnosis_note ? (
                  <p className="muted small">{t("doctorPatients.note", { note: prescription.diagnosis_note })}</p>
                ) : null}
                <ul className="clean-list">
                  {prescription.items.map((item) => (
                    <li key={item.id}>
                      {item.medicine_text} —{" "}
                      {t("doctorPatients.dispensedCount", {
                        dispensed: item.quantity_dispensed,
                        prescribed: item.quantity_prescribed,
                        unit: item.unit
                      })}
                      {item.dosage_instructions ? ` · ${item.dosage_instructions}` : ""}
                    </li>
                  ))}
                </ul>
                {prescription.dispenses.length > 0 ? (
                  <p className="muted small">
                    {t("doctorPatients.dispensedAt", {
                      pharmacies: prescription.dispenses.map((entry) => entry.pharmacy_name).join(", ")
                    })}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
