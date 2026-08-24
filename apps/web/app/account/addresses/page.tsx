"use client";

import { useState } from "react";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { AddressCard } from "@/components/account/SettingsParts";
import { AddressFormDialog } from "@/components/account/AddressForm";
import { ConfirmDialog } from "@/components/patient/Dialog";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useCurrentUser } from "@/lib/auth";
import { refillsUsingAddress, useAccount, useRefills } from "@/lib/patient/store";
import { plural } from "@/lib/patient/format";
import type { Address } from "@/lib/patient/types";

/**
 * Delivery addresses.
 *
 * The only real complication here is deletion. An address can be the one a
 * recurring refill delivers to, and quietly breaking a schedule is worse than
 * refusing the delete, so the confirmation names what depends on it.
 */
export default function AddressesPage() {
  const { user } = useCurrentUser();
  const account = useAccount();
  const { refills } = useRefills();
  const { notify } = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Address | null>(null);
  const [deleting, setDeleting] = useState<Address | null>(null);

  const affected = deleting ? refillsUsingAddress(refills, deleting.id) : [];

  return (
    <PatientShell initials={initialsFor(user?.first_name ?? account.profile.firstName, user?.last_name)}>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead
          title="Addresses"
          back={{ href: "/account", label: "Account" }}
          actions={
            <button
              type="button"
              className="hc-btn hc-btn-secondary"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Icon name="plus" size={16} />
              Add address
            </button>
          }
        />

        {!account.ready ? (
          <CardSkeletons count={2} lines={2} />
        ) : account.addresses.length === 0 ? (
          <EmptyPanel
            icon="pin"
            title="No delivery addresses yet"
            body="Add the places you want your medication delivered to, so checkout is a single tap."
          >
            <button type="button" className="hc-btn hc-btn-primary" onClick={() => setFormOpen(true)}>
              Add address
            </button>
          </EmptyPanel>
        ) : (
          <div className="hc-stack">
            {account.addresses.map((address) => (
              <AddressCard
                key={address.id}
                address={address}
                onEdit={() => {
                  setEditing(address);
                  setFormOpen(true);
                }}
                onDelete={() => setDeleting(address)}
                onSetDefault={() => {
                  account.setDefaultAddress(address.id);
                  notify(`${address.label} is now your default address`);
                }}
              />
            ))}
          </div>
        )}
      </div>

      {formOpen ? (
        <AddressFormDialog
          open
          address={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
          onSave={(address) => {
            account.saveAddress(address);
            notify(editing ? "Address updated" : "Address added");
          }}
          makeDefaultByDefault={account.addresses.length === 0}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          open
          onClose={() => setDeleting(null)}
          title={`Delete ${deleting.label}?`}
          body="This address will no longer be offered at checkout."
          consequence={
            affected.length > 0
              ? `${plural(affected.length, "upcoming refill")} currently deliver here. Move them to another address or they will need one chosen before the next delivery.`
              : undefined
          }
          confirmLabel="Delete address"
          tone="danger"
          onConfirm={() => {
            account.removeAddress(deleting.id);
            notify(`${deleting.label} deleted`);
          }}
        />
      ) : null}
    </PatientShell>
  );
}
