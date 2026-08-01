"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { QrScanner } from "@/components/rx/QrScanner";

/**
 * Entry point for a pharmacy holding a patient's prescription QR.
 * No account, no login: scan the code, or type the code and PIN from the printout.
 */
export default function PrescriptionEntryPage() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");

  function submitManual(event: FormEvent) {
    event.preventDefault();
    const cleaned = code.trim().toUpperCase();
    if (!cleaned || pin.trim().length < 4) {
      setError("Enter the prescription code and the 6-digit PIN.");
      return;
    }
    router.push(`/rx/${encodeURIComponent(cleaned)}?pin=${encodeURIComponent(pin.trim())}`);
  }

  function onScanned(value: string) {
    setScanning(false);
    setError("");
    try {
      // The QR holds a full URL; accept a bare code too, in case of a re-printed label.
      const url = new URL(value);
      const parts = url.pathname.split("/").filter(Boolean);
      const scannedCode = parts[parts.length - 1];
      const key = url.searchParams.get("k") || "";
      router.push(`/rx/${encodeURIComponent(scannedCode)}${key ? `?k=${encodeURIComponent(key)}` : ""}`);
    } catch {
      const bare = value.trim().toUpperCase();
      if (/^RX-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(bare)) {
        setCode(bare);
        setError("Code read from the QR. Enter the PIN to continue.");
      } else {
        setError("That QR code is not a PharmaLink prescription.");
      }
    }
  }

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>PharmaLink</span>
        </Link>
        <Link className="button button-secondary" href="/login">
          Pharmacy login
        </Link>
      </header>

      <main className="public-main narrow">
        <section className="panel">
          <div className="section-header">
            <div>
              <h1>Dispense a prescription</h1>
              <p>
                Any pharmacy can use this page. You do not need a PharmaLink account, and you do not need to
                register to consume a prescription.
              </p>
            </div>
          </div>

          {error ? <Notice tone={error.startsWith("Code read") ? "info" : "danger"}>{error}</Notice> : null}

          <div className="rx-entry-grid">
            <div className="rx-entry-card">
              <h3>1. Scan the QR code</h3>
              <p className="muted">Point the camera at the QR in the patient&apos;s email or printout.</p>
              {scanning ? (
                <QrScanner onResult={onScanned} onError={(message) => { setScanning(false); setError(message); }} />
              ) : (
                <Button type="button" onClick={() => { setError(""); setScanning(true); }}>
                  Open camera
                </Button>
              )}
              <p className="muted small">
                If the camera is unavailable, open the link in the patient&apos;s email on any phone, or use the
                manual option.
              </p>
            </div>

            <div className="rx-entry-card">
              <h3>2. Or enter it by hand</h3>
              <form onSubmit={submitManual} className="stacked-form">
                <Field label="Prescription code">
                  <input
                    value={code}
                    onChange={(event) => setCode(event.target.value.toUpperCase())}
                    placeholder="RX-XXXX-XXXX"
                    autoComplete="off"
                    spellCheck={false}
                  />
                </Field>
                <Field label="PIN (6 digits)">
                  <input
                    value={pin}
                    onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000"
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </Field>
                <Button type="submit">Open prescription</Button>
              </form>
            </div>
          </div>

          <Notice>
            The code alone is not enough to open a prescription: the QR key or the PIN is always required.
            Repeated wrong attempts lock the prescription for a short period, and every access is logged for
            the prescribing doctor.
          </Notice>
        </section>
      </main>
    </div>
  );
}
