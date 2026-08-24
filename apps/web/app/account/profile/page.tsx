"use client";

import { useEffect, useState } from "react";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, PageHead } from "@/components/patient/Page";
import { TextField } from "@/components/site/FormField";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useCurrentUser } from "@/lib/auth";
import { profileFor, useAccount } from "@/lib/patient/store";
import type { PatientProfile } from "@/lib/patient/types";

/**
 * Personal details.
 *
 * Read-only until the patient asks to edit, which keeps the common case (coming
 * to check a number) from looking like a form that needs filling in. Only the
 * four fields the account model actually carries are here; a medication
 * platform has no business collecting a health profile it does not use.
 */
export default function ProfilePage() {
  const { user } = useCurrentUser();
  const account = useAccount();
  const { notify } = useToast();

  // The signed-in account is the authority on name and email, so the screen
  // shows and edits those rather than the seed underneath them.
  const profile = profileFor(account.profile, user);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PatientProfile>(profile);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(profile);
    // `profile` is derived per render; the stored profile and the signed-in
    // user are the values that actually change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.profile, user, editing]);

  function set<K extends keyof PatientProfile>(key: K, value: PatientProfile[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!draft.firstName.trim()) found.firstName = "Enter your first name.";
    if (!draft.lastName.trim()) found.lastName = "Enter your last name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) found.email = "Enter a valid email address.";
    if (draft.phone.trim().length < 6) found.phone = "Enter a phone number the driver can reach you on.";

    setErrors(found);
    if (Object.keys(found).length > 0) return;

    account.saveProfile({
      firstName: draft.firstName.trim(),
      lastName: draft.lastName.trim(),
      email: draft.email.trim(),
      phone: draft.phone.trim()
    });
    setEditing(false);
    setSaved(true);
    notify("Profile updated");
  }

  const initials = initialsFor(profile.firstName, profile.lastName);

  return (
    <PatientShell initials={initials}>
      <div className="hc-wrap hc-page hc-wrap-narrow">
        <PageHead
          title="Profile"
          back={{ href: "/account", label: "Account" }}
          actions={
            !editing && account.ready ? (
              <button type="button" className="hc-btn hc-btn-secondary" onClick={() => setEditing(true)}>
                <Icon name="pencil" size={16} />
                Edit
              </button>
            ) : null
          }
        />

        {!account.ready ? (
          <CardSkeletons count={1} lines={4} />
        ) : editing ? (
          <form className="hc-card hc-form" onSubmit={save} noValidate>
            <div className="hc-form-row">
              <TextField
                label="First name"
                value={draft.firstName}
                onChange={(value) => set("firstName", value)}
                error={errors.firstName}
                required
                autoComplete="given-name"
              />
              <TextField
                label="Last name"
                value={draft.lastName}
                onChange={(value) => set("lastName", value)}
                error={errors.lastName}
                required
                autoComplete="family-name"
              />
            </div>
            <TextField
              type="email"
              label="Email"
              value={draft.email}
              onChange={(value) => set("email", value)}
              error={errors.email}
              required
              autoComplete="email"
              hint="Order and delivery updates are sent here."
            />
            <TextField
              label="Phone"
              value={draft.phone}
              onChange={(value) => set("phone", value)}
              error={errors.phone}
              required
              autoComplete="tel"
              hint="Drivers call this number if they cannot find your address."
            />

            <div className="hc-actions">
              <button type="submit" className="hc-btn hc-btn-primary">
                Save changes
              </button>
              <button
                type="button"
                className="hc-btn hc-btn-quiet"
                onClick={() => {
                  setDraft(profile);
                  setErrors({});
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="hc-card">
            <dl className="hc-kv">
              <div>
                <dt>First name</dt>
                <dd>{profile.firstName}</dd>
              </div>
              <div>
                <dt>Last name</dt>
                <dd>{profile.lastName}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{profile.email}</dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd className="hc-num">{profile.phone}</dd>
              </div>
            </dl>

            {saved ? (
              <p className="hc-inline-note" role="status" style={{ marginTop: 18 }}>
                <Icon name="check" size={16} strokeWidth={2.2} />
                Your details are up to date.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </PatientShell>
  );
}
