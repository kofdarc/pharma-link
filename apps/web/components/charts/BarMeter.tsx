"use client";

/**
 * A single magnitude bar with its own label and value.
 *
 * Why a meter rather than a chart: each of these answers one question about one
 * quantity, so a bar plus a number beats a pie or a multi-series chart. Identity comes
 * from the label, never from colour, which is why several meters can share one hue
 * without becoming an (unvalidated) categorical palette.
 *
 * `intensity` selects a step on the single-hue sequential ramp. Use it only when the
 * series is genuinely ordinal (A/B/C classes); leave it default otherwise.
 */
export function BarMeter({
  label,
  value,
  max,
  caption,
  intensity = "base",
  valueLabel
}: {
  label: string;
  value: number;
  max: number;
  caption?: string;
  intensity?: "light" | "base" | "dark";
  valueLabel?: string;
}) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;

  return (
    <div className="meter">
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <strong className="meter-value">{valueLabel ?? `${Math.round(percent)}%`}</strong>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`${label}: ${valueLabel ?? `${Math.round(percent)}%`}`}
      >
        {/* Rounded data-end only, anchored flat to the baseline at the start. */}
        <div className={`meter-fill meter-fill-${intensity}`} style={{ width: `${percent}%` }} />
      </div>
      {caption ? <small className="muted">{caption}</small> : null}
    </div>
  );
}
