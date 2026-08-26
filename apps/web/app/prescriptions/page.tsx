"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead, Segmented } from "@/components/patient/Page";
import { PrescriptionCard } from "@/components/prescriptions/PrescriptionParts";
import { usePrescriptions } from "@/lib/patient/store";
import type { Prescription } from "@/lib/patient/types";

type Tab = "active" | "completed" | "expired";

/**
 * Prescriptions the patient holds.
 *
 * Framed as a wallet rather than a medical record: the list answers "what can I
 * still get" first, and everything clinical stays on the detail screen. Active
 * covers both untouched and partly collected prescriptions, because from the
 * patient's side those are the same thing, something they can still order from.
 */
const TABS: { value: Tab; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "completed", label: "Completed" },
  { value: "expired", label: "Expired" }
];

function bucket(prescription: Prescription): Tab {
  if (prescription.status === "expired") return "expired";
  if (prescription.status === "completed") return "completed";
  return "active";
}

export default function PrescriptionsPage() {
  const { prescriptions, ready } = usePrescriptions();
  const [tab, setTab] = useState<Tab>("active");

  const counts = useMemo(() => {
    return prescriptions.reduce(
      (totals, prescription) => ({ ...totals, [bucket(prescription)]: totals[bucket(prescription)] + 1 }),
      { active: 0, completed: 0, expired: 0 } as Record<Tab, number>
    );
  }, [prescriptions]);

  const visible = useMemo(
    () =>
      prescriptions
        .filter((prescription) => bucket(prescription) === tab)
        .sort((a, b) => b.issuedOn.localeCompare(a.issuedOn)),
    [prescriptions, tab]
  );

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <PageHead
          title="Prescriptions"
          lead="Prescriptions your physicians issued through HealthConnect, and what is left to collect on each."
        />

        <Segmented
          label="Prescription status"
          value={tab}
          onChange={setTab}
          options={TABS.map((entry) => ({ ...entry, count: counts[entry.value] }))}
        />

        <div className="hc-page-body">
          {!ready ? (
            <CardSkeletons count={2} />
          ) : visible.length > 0 ? (
            <div className="hc-cardgrid">
              {visible.map((prescription) => (
                <PrescriptionCard key={prescription.id} prescription={prescription} />
              ))}
            </div>
          ) : (
            <EmptyState tab={tab} />
          )}
        </div>
      </div>
    </PatientShell>
  );
}

/**
 * Nothing is invented to fill these. An empty prescription list is a normal
 * state for a healthy person, and a placeholder prescription would be a lie
 * about their own medical record.
 */
function EmptyState({ tab }: { tab: Tab }) {
  if (tab === "active") {
    return (
      <EmptyPanel
        icon="rx"
        title="No active prescriptions"
        body="New digital prescriptions issued to you will appear here, along with how much of each you can still collect."
      >
        <Link href="/how-it-works" className="hc-btn hc-btn-secondary">
          How prescriptions work
        </Link>
      </EmptyPanel>
    );
  }

  if (tab === "completed") {
    return (
      <EmptyPanel
        icon="check"
        title="Nothing fully collected yet"
        body="Once every medication on a prescription has been collected, it moves here."
      />
    );
  }

  return (
    <EmptyPanel
      icon="clock"
      title="No expired prescriptions"
      body="Prescriptions move here after their validity date passes, whether or not everything on them was collected."
    />
  );
}
