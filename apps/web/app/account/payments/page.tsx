"use client";

import { useState } from "react";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, PageHead } from "@/components/patient/Page";
import { PaymentMethodCard } from "@/components/account/SettingsParts";
import { ConfirmDialog, Dialog } from "@/components/patient/Dialog";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useAccount } from "@/lib/patient/store";
import type { PaymentMethod } from "@/lib/patient/types";

/**
 * Payment methods.
 *
 * Structured UI over demo state, and nothing more. There is no payment
 * processor behind this build, so the page does not ask for a card number, does
 * not store one, and says which of those two facts matters to the patient. When
 * a processor is integrated, adding a card becomes its hosted form and this
 * screen keeps its shape.
 */
export default function PaymentsPage() {
  const account = useAccount();
  const { notify } = useToast();

  const [addOpen, setAddOpen] = useState(false);
  const [removing, setRemoving] = useState<PaymentMethod | null>(null);

  return (
    <PatientShell>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead
          title="Payment methods"
          back={{ href: "/account", label: "Account" }}
          actions={
            <button type="button" className="hc-btn hc-btn-secondary" onClick={() => setAddOpen(true)}>
              <Icon name="plus" size={16} />
              Add method
            </button>
          }
        />

        {!account.ready ? (
          <CardSkeletons count={2} lines={2} />
        ) : (
          <div className="hc-stack">
            {account.payments.map((method) => (
              <PaymentMethodCard
                key={method.id}
                method={method}
                onSetDefault={() => {
                  account.setDefaultPayment(method.id);
                  notify("Default payment method updated");
                }}
                onRemove={() => setRemoving(method)}
              />
            ))}
          </div>
        )}

        <p className="hc-small hc-page-foot">
          HealthConnect never shows a full card number. Cash on delivery is always available and cannot be removed.
        </p>
      </div>

      <Dialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add a payment method"
        size="sm"
        footer={
          <button type="button" className="hc-btn hc-btn-secondary hc-btn-block" onClick={() => setAddOpen(false)}>
            Close
          </button>
        }
      >
        <p className="hc-body">
          Card payments are not connected in this build, so there is nothing to enter here yet. Cash on delivery works
          today and is available at checkout.
        </p>
        <p className="hc-inline-note" style={{ marginTop: 16 }}>
          <Icon name="lock" size={15} />
          When card payments are switched on, card details will be entered with the payment provider and never stored by
          HealthConnect.
        </p>
      </Dialog>

      {removing ? (
        <ConfirmDialog
          open
          onClose={() => setRemoving(null)}
          title="Remove this payment method?"
          body={`${removing.brand} ending ${removing.last4} will no longer be offered at checkout.`}
          consequence={
            removing.isDefault ? "It is your default method, so another one will be made default automatically." : undefined
          }
          confirmLabel="Remove"
          tone="danger"
          onConfirm={() => {
            account.removePayment(removing.id);
            notify("Payment method removed");
          }}
        />
      ) : null}
    </PatientShell>
  );
}
