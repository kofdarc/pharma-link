"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Doctor } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";

export default function DoctorProfilePage() {
  const t = useTranslations();
  const [doctor, setDoctor] = useState<Doctor | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Doctor>("/doctor/profile/")
      .then(setDoctor)
      .catch(() => setError(t("doctorProfile.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!doctor) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{doctor.full_name}</h1>
          <p className="muted">
            {doctor.specialty || t("doctorProfile.generalPractice")} · {t("doctorProfile.licence", { number: doctor.license_number })}
          </p>
        </div>
        <Badge tone={doctor.is_active ? "success" : "danger"}>
          {doctor.is_active ? t("doctorProfile.active") : t("doctorProfile.suspended")}
        </Badge>
      </div>

      {!doctor.is_active ? <Notice tone="danger">{t("doctorProfile.suspendedNotice")}</Notice> : null}

      <section className="panel">
        <h3>{t("doctorProfile.contact")}</h3>
        <dl className="detail-grid">
          <div>
            <dt>{t("doctorProfile.email")}</dt>
            <dd>{doctor.email}</dd>
          </div>
          <div>
            <dt>{t("doctorProfile.phone")}</dt>
            <dd>{doctor.phone || t("doctorProfile.notRecorded")}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h3>{t("doctorProfile.clinic")}</h3>
        <dl className="detail-grid">
          <div>
            <dt>{t("doctorProfile.name")}</dt>
            <dd>{doctor.clinic_name || t("doctorProfile.notRecorded")}</dd>
          </div>
          <div>
            <dt>{t("doctorProfile.address")}</dt>
            <dd>{doctor.clinic_address || t("doctorProfile.notRecorded")}</dd>
          </div>
          <div>
            <dt>{t("doctorProfile.area")}</dt>
            <dd>{doctor.clinic_area || t("doctorProfile.notRecorded")}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h3>{t("doctorProfile.licenceSection")}</h3>
        <dl className="detail-grid">
          <div>
            <dt>{t("doctorProfile.licenceNumber")}</dt>
            <dd>{doctor.license_number}</dd>
          </div>
          <div>
            <dt>{t("doctorProfile.activated")}</dt>
            <dd>{doctor.activated_at ? new Date(doctor.activated_at).toLocaleDateString() : t("doctorProfile.notActivated")}</dd>
          </div>
        </dl>
        <p className="muted small">{t("doctorProfile.rosterNote")}</p>
      </section>
    </>
  );
}
