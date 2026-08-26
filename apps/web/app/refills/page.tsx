"use client";

import { useState } from "react";
import Link from "next/link";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { RefillCard, RefillScheduleDialog } from "@/components/refills/RefillParts";
import { ConfirmDialog } from "@/components/patient/Dialog";
import { useToast } from "@/components/patient/Toast";
import { useAccount, usePrescriptions, useRefills } from "@/lib/patient/store";
import type { Refill } from "@/lib/patient/types";

/**
 * Recurring refills.
 *
 * Not promoted anywhere in the product. A repeating medication delivery is
 * something a patient opts into for a condition they already manage, so this
 * page waits to be visited rather than pushing anyone to sign up.
 */
export default function RefillsPage() {
  const { refills, ready, setStatus, updateRefill, refillNow } = useRefills();
  const { prescriptions } = usePrescriptions();
  const account = useAccount();
  const { notify } = useToast();

  const [managing, setManaging] = useState<Refill | null>(null);
  const [cancelling, setCancelling] = useState<Refill | null>(null);

  const active = refills.filter((refill) => refill.status === "active");
  const paused = refills.filter((refill) => refill.status === "paused");

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <PageHead title="Refills" lead="Keep track of the medicines you need regularly." />

        <div className="hc-page-body">
          {!ready ? (
            <CardSkeletons count={2} />
          ) : refills.length === 0 ? (
            <EmptyPanel
              icon="refresh"
              title="No recurring refills yet"
              body="Medicines you choose to receive regularly will appear here, with the date of the next delivery."
            >
              <Link href="/orders" className="hc-btn hc-btn-secondary">
                View your orders
              </Link>
            </EmptyPanel>
          ) : (
            <>
              {active.length > 0 ? (
                <section aria-labelledby="refills-active">
                  <h2 className="hc-section-label" id="refills-active">
                    Scheduled
                  </h2>
                  <div className="hc-cardgrid">
                    {active.map((refill) => (
                      <RefillCard
                        key={refill.id}
                        refill={refill}
                        prescriptions={prescriptions}
                        address={account.addresses.find((entry) => entry.id === refill.addressId)}
                        onManage={() => setManaging(refill)}
                        onResume={() => setStatus(refill.id, "active")}
                        onRefillNow={() => {
                          refillNow(refill.id);
                          notify(`${refill.name} refill requested`);
                        }}
                      />
                    ))}
                  </div>
                </section>
              ) : null}

              {paused.length > 0 ? (
                <section aria-labelledby="refills-paused">
                  <h2 className="hc-section-label" id="refills-paused">
                    Paused
                  </h2>
                  <div className="hc-cardgrid">
                    {paused.map((refill) => (
                      <RefillCard
                        key={refill.id}
                        refill={refill}
                        prescriptions={prescriptions}
                        address={account.addresses.find((entry) => entry.id === refill.addressId)}
                        onManage={() => setManaging(refill)}
                        onRefillNow={() => refillNow(refill.id)}
                        onResume={() => {
                          setStatus(refill.id, "active");
                          notify(`${refill.name} refill resumed`);
                        }}
                      />
                    ))}
                  </div>
                </section>
              ) : null}

              <p className="hc-small hc-page-foot">
                A scheduled refill still needs a valid prescription at the time it is filled. HealthConnect will tell you
                if one is about to run out, but only your physician can renew it.
              </p>
            </>
          )}
        </div>
      </div>

      {managing ? (
        <RefillScheduleDialog
          open
          refill={managing}
          addresses={account.addresses}
          onClose={() => setManaging(null)}
          onSave={(patch) => {
            updateRefill(managing.id, patch);
            notify("Refill schedule updated");
          }}
          onPause={() => {
            setStatus(managing.id, "paused");
            notify(`${managing.name} refill paused`);
          }}
          onCancel={() => {
            setCancelling(managing);
            setManaging(null);
          }}
        />
      ) : null}

      {cancelling ? (
        <ConfirmDialog
          open
          onClose={() => setCancelling(null)}
          title="Cancel this refill?"
          body={`${cancelling.name} will no longer be delivered automatically. You can still order it whenever you need it.`}
          consequence="Cancelling removes the schedule. Setting it up again later starts from scratch."
          confirmLabel="Cancel refill"
          tone="danger"
          onConfirm={() => {
            setStatus(cancelling.id, "cancelled");
            notify(`${cancelling.name} refill cancelled`);
          }}
        />
      ) : null}
    </PatientShell>
  );
}
