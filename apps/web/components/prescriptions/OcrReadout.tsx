import type { OcrFields } from "@/lib/patient/types";

/**
 * The OCR read of a prescription scan, shown read-only.
 *
 * Renders nothing until at least one field has a value - a blank grid of dashes
 * would just be noise. Used on the upload form (preview, before submit) and on
 * the Prescriptions list (after submit), so the copy is passed in.
 *
 * When `lowConfidence` is set the read exists but is too weak to trust (a mangled
 * handwriting scan), so the parsed details are withheld and a short notice is shown
 * in their place - the scan still goes to a pharmacist either way.
 */
export function OcrReadout({
  fields,
  lowConfidence = false,
  title = "What we read from your prescription",
  footnote = "These were read automatically. A pharmacist checks them against your photo before dispensing."
}: {
  fields: OcrFields | null;
  lowConfidence?: boolean;
  title?: string;
  footnote?: string;
}) {
  if (lowConfidence) {
    return (
      <div className="hc-details">
        <p className="hc-card-label">{title}</p>
        <p className="hc-small">
          This prescription is handwritten, so we haven&apos;t shown the details here. Your photo
          has been received and a pharmacist will read it directly and confirm everything with you
          before dispensing.
        </p>
      </div>
    );
  }

  if (!fields) return null;

  const header: [string, string][] = [
    ["Patient", fields.patientName],
    ["Phone", fields.patientPhone],
    ["Prescriber", fields.doctorName],
    ["Date", fields.prescriptionDate]
  ];
  const shownHeader = header.filter(([, value]) => value);
  const meds = fields.medications.filter((med) => med.name);

  if (shownHeader.length === 0 && meds.length === 0) return null;

  return (
    <div className="hc-details">
      <p className="hc-card-label">{title}</p>

      {shownHeader.length > 0 ? (
        <dl className="hc-kv">
          {shownHeader.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {meds.length > 0 ? (
        <ul className="hc-plainlist">
          {meds.map((med, index) => (
            <li key={`${med.name}-${index}`}>
              <strong>
                {med.name}
                {med.strength ? ` ${med.strength}` : ""}
              </strong>
              {med.quantity != null ? ` · ${med.quantity}` : ""}
              {med.directions || med.dosePattern ? (
                <>
                  <br />
                  <span className="hc-small">
                    {med.directions || med.dosePattern}
                    {/* The prescriber's own shorthand, kept beside the plain reading so the
                        patient can check it against the page rather than trusting the
                        expansion. Suppressed when there is nothing to expand. */}
                    {med.directions && med.dosePattern ? ` · written as ${med.dosePattern}` : ""}
                  </span>
                </>
              ) : null}
              {med.duration || med.refills != null ? (
                <>
                  <br />
                  <span className="hc-small">
                    {med.duration ? `For ${med.duration}` : ""}
                    {med.duration && med.refills != null ? " · " : ""}
                    {med.refills != null ? `${med.refills} refill${med.refills === 1 ? "" : "s"}` : ""}
                  </span>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {fields.notes ? <p className="hc-small">{fields.notes}</p> : null}

      {footnote ? <p className="hc-small">{footnote}</p> : null}
    </div>
  );
}
