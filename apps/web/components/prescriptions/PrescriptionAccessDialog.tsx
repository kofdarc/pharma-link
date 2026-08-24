"use client";

import { useEffect, useMemo, useState } from "react";
import { Dialog } from "@/components/patient/Dialog";
import { Icon } from "@/components/ui/Icon";
import type { Prescription } from "@/lib/patient/types";

/**
 * Prescription access, shown only when the patient asks for it.
 *
 * This is the one screen in the patient area that puts a credential on glass,
 * so it is behind an explicit action, it never appears in a list or a preview,
 * and the PIN stays masked until it is separately revealed. Closing the dialog
 * re-masks it: leaving a PIN uncovered because a dialog was reopened is exactly
 * the kind of quiet leak this treatment exists to prevent.
 */

const GRID = 21;

/**
 * A stand-in code pattern, derived from the prescription reference so it looks
 * the same every time it is opened.
 *
 * It is not a scannable code and the dialog says so. Rendering something that
 * merely resembles a working code without saying it is a placeholder would be
 * the kind of fake capability this product should not ship.
 */
function useCodePattern(seed: string): boolean[] {
  return useMemo(() => {
    let state = 0;
    for (let index = 0; index < seed.length; index += 1) state = (state * 31 + seed.charCodeAt(index)) >>> 0;

    const cells: boolean[] = [];
    for (let index = 0; index < GRID * GRID; index += 1) {
      state = (state * 1664525 + 1013904223) >>> 0;
      cells.push((state >>> 16) % 100 < 46);
    }

    // The three corner squares that make the shape read as a code at a glance.
    const finder = (row: number, column: number) => {
      for (let y = 0; y < 7; y += 1) {
        for (let x = 0; x < 7; x += 1) {
          const edge = y === 0 || y === 6 || x === 0 || x === 6;
          const core = y >= 2 && y <= 4 && x >= 2 && x <= 4;
          cells[(row + y) * GRID + (column + x)] = edge || core;
        }
      }
    };
    finder(0, 0);
    finder(0, GRID - 7);
    finder(GRID - 7, 0);

    return cells;
  }, [seed]);
}

export function PrescriptionAccessDialog({
  prescription,
  open,
  onClose
}: {
  prescription: Prescription;
  open: boolean;
  onClose: () => void;
}) {
  const [pinVisible, setPinVisible] = useState(false);
  const cells = useCodePattern(prescription.id);

  useEffect(() => {
    if (!open) setPinVisible(false);
  }, [open]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Prescription access"
      description="Show this at a participating pharmacy when they ask for your prescription."
      size="sm"
      footer={
        <button type="button" className="hc-btn hc-btn-secondary hc-btn-block" onClick={onClose}>
          Done
        </button>
      }
    >
      <div className="hc-access">
        <div className="hc-access-code">
          <svg viewBox={`0 0 ${GRID} ${GRID}`} role="img" aria-label={`Access code for prescription ${prescription.id}`}>
            <rect width={GRID} height={GRID} fill="#fff" />
            {cells.map((filled, index) =>
              filled ? (
                <rect key={index} x={index % GRID} y={Math.floor(index / GRID)} width="1" height="1" fill="#0e2530" />
              ) : null
            )}
          </svg>
        </div>

        <p className="hc-access-ref hc-num">{prescription.id}</p>
        <p className="hc-small">Demonstration code. It is not scannable in this build.</p>

        <div className="hc-access-pin">
          <div>
            <p className="hc-card-label">Access PIN</p>
            <p className="hc-access-pin-value hc-num">{pinVisible ? prescription.accessPin : "••• •••"}</p>
          </div>
          <button
            type="button"
            className="hc-btn hc-btn-secondary hc-btn-sm"
            onClick={() => setPinVisible((value) => !value)}
            aria-pressed={pinVisible}
          >
            <Icon name={pinVisible ? "eyeOff" : "eye"} size={15} />
            {pinVisible ? "Hide" : "Show"}
          </button>
        </div>

        <p className="hc-inline-note">
          <Icon name="lock" size={15} />
          Only show this when you are ready to use your prescription.
        </p>
      </div>
    </Dialog>
  );
}
