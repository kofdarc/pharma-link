"use client";

import { useState } from "react";
import { Dialog } from "@/components/patient/Dialog";
import { TextField } from "@/components/site/FormField";
import type { Address } from "@/lib/patient/types";

/**
 * Adding or editing a delivery address.
 *
 * Kept to what a driver in Beirut actually needs to find a door: a street line,
 * the building and floor, the area, and a free note. No country selector, no
 * postcode, no state field. International address handling can arrive with
 * international delivery.
 *
 * Lives here rather than in the checkout so that both the account screen and
 * the checkout use the same form and the same validation.
 */

const EMPTY: Omit<Address, "id"> = {
  label: "",
  line1: "",
  building: "",
  area: "",
  city: "Beirut",
  notes: "",
  isDefault: false
};

export function AddressFormDialog({
  open,
  onClose,
  onSave,
  address,
  makeDefaultByDefault = false
}: {
  open: boolean;
  onClose: () => void;
  onSave: (address: Address) => void;
  address?: Address | null;
  makeDefaultByDefault?: boolean;
}) {
  const editing = Boolean(address);
  const [draft, setDraft] = useState<Omit<Address, "id">>(
    address ? { ...address } : { ...EMPTY, isDefault: makeDefaultByDefault }
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  function set<K extends keyof Omit<Address, "id">>(key: K, value: Omit<Address, "id">[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!draft.label.trim()) found.label = "Give this address a name, such as Home or Work.";
    if (!draft.line1.trim()) found.line1 = "Enter the street address.";
    if (!draft.area.trim()) found.area = "Enter the area.";
    if (!draft.city.trim()) found.city = "Enter the city.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    onSave({
      ...draft,
      id: address?.id ?? `addr-${Date.now().toString(36)}`,
      label: draft.label.trim(),
      line1: draft.line1.trim(),
      area: draft.area.trim(),
      city: draft.city.trim()
    });
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? "Edit address" : "Add address"}
      footer={
        <>
          <button type="button" className="hc-btn hc-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="address-form" className="hc-btn hc-btn-primary">
            {editing ? "Save address" : "Add address"}
          </button>
        </>
      }
    >
      <form className="hc-form" id="address-form" onSubmit={submit} noValidate>
        <TextField
          label="Name"
          value={draft.label}
          onChange={(value) => set("label", value)}
          error={errors.label}
          required
          placeholder="Home"
        />
        <TextField
          label="Street address"
          value={draft.line1}
          onChange={(value) => set("line1", value)}
          error={errors.line1}
          required
          autoComplete="address-line1"
        />
        <TextField
          label="Building and floor"
          value={draft.building ?? ""}
          onChange={(value) => set("building", value)}
          autoComplete="address-line2"
        />
        <div className="hc-form-row">
          <TextField
            label="Area"
            value={draft.area}
            onChange={(value) => set("area", value)}
            error={errors.area}
            required
            autoComplete="address-level2"
          />
          <TextField
            label="City"
            value={draft.city}
            onChange={(value) => set("city", value)}
            error={errors.city}
            required
            autoComplete="address-level1"
          />
        </div>
        <TextField
          label="Delivery notes"
          value={draft.notes ?? ""}
          onChange={(value) => set("notes", value)}
          hint="Anything that helps the driver find you, such as a gate code or a landmark."
        />

        <label className="hc-check">
          <input
            type="checkbox"
            checked={draft.isDefault}
            onChange={(event) => set("isDefault", event.target.checked)}
          />
          Deliver here by default
        </label>
      </form>
    </Dialog>
  );
}
