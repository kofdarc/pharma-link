"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { usePatientUser } from "@/components/site/PatientGuard";
import { PageHead } from "@/components/patient/Page";
import { SettingsRow, SettingsSection } from "@/components/account/SettingsParts";
import { ConfirmDialog } from "@/components/patient/Dialog";
import { signOut } from "@/lib/auth";
import { profileFor, useAccount } from "@/lib/patient/store";
import { plural } from "@/lib/patient/format";

/**
 * The account hub.
 *
 * A directory, not a dashboard. Nothing sensitive is previewed here: the row
 * for prescriptions does not summarise them, the payment row does not show a
 * card, and the account name is the only personal detail on the page.
 */
export default function AccountPage() {
  const router = useRouter();
  const user = usePatientUser();
  const account = useAccount();
  const [signOutOpen, setSignOutOpen] = useState(false);

  const profile = profileFor(account.profile, user);
  const { firstName, lastName, email } = profile;
  const cards = account.payments.filter((method) => method.kind === "card");

  return (
    <PatientShell>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead title="Account" />

        <div className="hc-identity">
          <span className="hc-identity-avatar" aria-hidden="true">
            {initialsFor(firstName, lastName)}
          </span>
          <div>
            <p className="hc-identity-name">
              {firstName} {lastName}
            </p>
            <p className="hc-small">{email}</p>
          </div>
        </div>

        <div className="hc-settings">
          <SettingsSection title="Personal">
            <SettingsRow href="/account/profile" icon="user" label="Profile" />
            <SettingsRow
              href="/account/addresses"
              icon="pin"
              label="Addresses"
              value={plural(account.addresses.length, "address", "addresses")}
            />
          </SettingsSection>

          <SettingsSection title="Payments">
            <SettingsRow
              href="/account/payments"
              icon="card"
              label="Payment methods"
              value={cards.length > 0 ? plural(cards.length, "card") : "Cash only"}
            />
          </SettingsSection>

          <SettingsSection title="Medication">
            <SettingsRow href="/prescriptions" icon="rx" label="Prescriptions" />
            <SettingsRow href="/refills" icon="refresh" label="Refills" />
            <SettingsRow href="/orders" icon="box" label="Orders" />
          </SettingsSection>

          <SettingsSection title="Preferences">
            <SettingsRow href="/account/notifications" icon="bell" label="Notifications" />
          </SettingsSection>

          <SettingsSection title="Security">
            <SettingsRow href="/account/security" icon="lock" label="Password and security" />
          </SettingsSection>

          <SettingsSection title="Support">
            <SettingsRow href="/how-it-works" icon="help" label="How HealthConnect works" />
            <SettingsRow href="/about" icon="people" label="About HealthConnect" />
          </SettingsSection>

          <SettingsSection title="Session">
            <SettingsRow icon="close" label="Sign out" tone="danger" onClick={() => setSignOutOpen(true)} />
          </SettingsSection>
        </div>
      </div>

      <ConfirmDialog
        open={signOutOpen}
        onClose={() => setSignOutOpen(false)}
        title="Sign out?"
        body="You will need to sign in again to see your prescriptions and orders on this device."
        confirmLabel="Sign out"
        onConfirm={() => {
          signOut();
          router.push("/login");
        }}
      />
    </PatientShell>
  );
}
