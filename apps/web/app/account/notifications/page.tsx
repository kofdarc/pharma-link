"use client";

import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, PageHead, Toggle } from "@/components/patient/Page";
import { useToast } from "@/components/patient/Toast";
import { useCurrentUser } from "@/lib/auth";
import { useAccount } from "@/lib/patient/store";
import type { NotificationPreferences } from "@/lib/patient/types";

/**
 * What HealthConnect is allowed to send.
 *
 * Operational messages and marketing are kept in separate groups on purpose.
 * Bundling "your driver is outside" with "our news" into one switch forces a
 * patient to choose between being marketed to and knowing where their medicine
 * is, which is not a real choice.
 */

const OPERATIONAL: { key: keyof NotificationPreferences; label: string; hint: string }[] = [
  { key: "orderUpdates", label: "Order updates", hint: "When a pharmacy accepts and starts preparing your order." },
  { key: "deliveryUpdates", label: "Delivery updates", hint: "When your order is collected and when the driver is close." },
  {
    key: "prescriptionReminders",
    label: "Prescription reminders",
    hint: "Before a prescription expires while medication is still uncollected."
  },
  { key: "refillReminders", label: "Refill reminders", hint: "A few days before a scheduled refill is due." }
];

export default function NotificationsPage() {
  const { user } = useCurrentUser();
  const account = useAccount();
  const { notify } = useToast();

  function set(key: keyof NotificationPreferences, value: boolean) {
    account.setNotifications({ ...account.notifications, [key]: value });
    notify("Notification preferences saved");
  }

  return (
    <PatientShell initials={initialsFor(user?.first_name ?? account.profile.firstName, user?.last_name)}>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead
          title="Notifications"
          back={{ href: "/account", label: "Account" }}
          lead="Choose what HealthConnect tells you about, and how much of it."
        />

        {!account.ready ? (
          <CardSkeletons count={2} lines={3} />
        ) : (
          <>
            <section className="hc-card" aria-labelledby="notif-operational">
              <h2 className="hc-section-label" id="notif-operational">
                Your medication
              </h2>
              <div className="hc-toggles">
                {OPERATIONAL.map((row) => (
                  <Toggle
                    key={row.key}
                    id={`notif-${row.key}`}
                    label={row.label}
                    hint={row.hint}
                    checked={account.notifications[row.key]}
                    onChange={(value) => set(row.key, value)}
                  />
                ))}
              </div>
            </section>

            <section className="hc-card" aria-labelledby="notif-marketing">
              <h2 className="hc-section-label" id="notif-marketing">
                From HealthConnect
              </h2>
              <div className="hc-toggles">
                <Toggle
                  id="notif-productNews"
                  label="Product and service emails"
                  hint="Occasional emails about new features and connected pharmacies. Off by default."
                  checked={account.notifications.productNews}
                  onChange={(value) => set("productNews", value)}
                />
              </div>
            </section>

            <p className="hc-small hc-page-foot">
              Messages about an order in progress are always sent, whatever is set here, because you need them to receive
              your delivery.
            </p>
          </>
        )}
      </div>
    </PatientShell>
  );
}
