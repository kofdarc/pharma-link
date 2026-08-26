"use client";

import { useState } from "react";
import { PatientShell } from "@/components/site/PatientShell";
import { PageHead } from "@/components/patient/Page";
import { Dialog } from "@/components/patient/Dialog";
import { PasswordField } from "@/components/site/FormField";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useAccount } from "@/lib/patient/store";

/**
 * Password and security.
 *
 * Only what this build genuinely supports. There is no two-factor enrolment, no
 * biometric unlock and no session registry behind the app, so none of them are
 * shown: a security screen that lists protections a patient does not actually
 * have is worse than a short one.
 *
 * The tone is reassuring rather than alarming. Nothing here is red, and nothing
 * warns about a threat the patient cannot act on.
 */
export default function SecurityPage() {
  const account = useAccount();
  const { notify } = useToast();

  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function reset() {
    setCurrent("");
    setNext("");
    setConfirm("");
    setErrors({});
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!current) found.current = "Enter your current password.";
    if (next.length < 10) found.next = "Use at least 10 characters.";
    if (next !== confirm) found.confirm = "The two passwords do not match.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setOpen(false);
    reset();
    notify("Password changed");
  }

  return (
    <PatientShell>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead title="Password and security" back={{ href: "/account", label: "Account" }} />

        <section className="hc-card">
          <div className="hc-card-head">
            <div>
              <h2 className="hc-h3">Password</h2>
              <p className="hc-small" style={{ marginTop: 5 }}>
                Used to sign in to HealthConnect on any device.
              </p>
            </div>
            <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={() => setOpen(true)}>
              Change password
            </button>
          </div>
        </section>

        <section className="hc-card hc-card-quiet">
          <p className="hc-cover-head">
            <Icon name="shield" size={16} />
            How your prescriptions are protected
          </p>
          <ul className="hc-plainlist">
            <li>
              <Icon name="check" size={14} strokeWidth={2.2} />
              Prescription access codes are only shown when you ask for them, and are never included in a link or a
              notification.
            </li>
            <li>
              <Icon name="check" size={14} strokeWidth={2.2} />
              A pharmacy sees only the prescription you present to them, not the rest of your account.
            </li>
            <li>
              <Icon name="check" size={14} strokeWidth={2.2} />
              Signing out on this device clears your session immediately.
            </li>
          </ul>
        </section>
      </div>

      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          reset();
        }}
        title="Change password"
        size="sm"
        footer={
          <>
            <button
              type="button"
              className="hc-btn hc-btn-secondary"
              onClick={() => {
                setOpen(false);
                reset();
              }}
            >
              Cancel
            </button>
            <button type="submit" form="password-form" className="hc-btn hc-btn-primary">
              Change password
            </button>
          </>
        }
      >
        <form className="hc-form" id="password-form" onSubmit={submit} noValidate>
          <PasswordField
            label="Current password"
            value={current}
            onChange={setCurrent}
            error={errors.current}
            required
            autoComplete="current-password"
          />
          <PasswordField
            label="New password"
            value={next}
            onChange={setNext}
            error={errors.next}
            required
            autoComplete="new-password"
            hint="At least 10 characters."
          />
          <PasswordField
            label="Confirm new password"
            value={confirm}
            onChange={setConfirm}
            error={errors.confirm}
            required
            autoComplete="new-password"
          />
        </form>
      </Dialog>
    </PatientShell>
  );
}
