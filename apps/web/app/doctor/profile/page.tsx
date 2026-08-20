"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import type { Doctor } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";

export default function DoctorProfilePage() {
  const [doctor, setDoctor] = useState<Doctor | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Doctor>("/doctor/profile/")
      .then(setDoctor)
      .catch(() => setError("Could not load your profile."));
  }, []);

  if (!doctor) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{doctor.full_name}</h1>
          <p className="muted">
            {doctor.specialty || "General practice"} · Licence {doctor.license_number}
          </p>
        </div>
        <Badge tone={doctor.is_active ? "success" : "danger"}>{doctor.is_active ? "Active" : "Suspended"}</Badge>
      </div>

      {!doctor.is_active ? (
        <Notice tone="danger">
          Your licence has been suspended by the platform. You will not be able to issue new prescriptions until it
          is reactivated.
        </Notice>
      ) : null}

      <section className="panel">
        <h3>Contact</h3>
        <dl className="detail-grid">
          <div>
            <dt>Email</dt>
            <dd>{doctor.email}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>{doctor.phone || "Not recorded"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h3>Clinic</h3>
        <dl className="detail-grid">
          <div>
            <dt>Name</dt>
            <dd>{doctor.clinic_name || "Not recorded"}</dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd>{doctor.clinic_address || "Not recorded"}</dd>
          </div>
          <div>
            <dt>Area</dt>
            <dd>{doctor.clinic_area || "Not recorded"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h3>Licence</h3>
        <dl className="detail-grid">
          <div>
            <dt>Licence number</dt>
            <dd>{doctor.license_number}</dd>
          </div>
          <div>
            <dt>Activated</dt>
            <dd>{doctor.activated_at ? new Date(doctor.activated_at).toLocaleDateString() : "Not activated"}</dd>
          </div>
        </dl>
        <p className="muted small">
          Profile details come from the Order of Physicians roster and cannot be edited here. Contact the platform
          if anything needs correcting.
        </p>
      </section>
    </>
  );
}
