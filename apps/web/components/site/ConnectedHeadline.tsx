"use client";

import { useEffect, useState } from "react";

const CONNECTED_WORDS = ["medications", "prescriptions", "pharmacies", "deliveries"] as const;
const FINALE_INDEX = CONNECTED_WORDS.length;
const WORD_DURATION_MS = 2400;
const FINALE_DURATION_MS = 4600;

export function ConnectedHeadline() {
  const [sequenceIndex, setSequenceIndex] = useState(0);
  const isFinale = sequenceIndex === FINALE_INDEX;

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const timeout = window.setTimeout(
      () => setSequenceIndex((current) => (current + 1) % (CONNECTED_WORDS.length + 1)),
      isFinale ? FINALE_DURATION_MS : WORD_DURATION_MS
    );

    return () => window.clearTimeout(timeout);
  }, [isFinale, sequenceIndex]);

  return (
    <h1 className="hc-display hc-connected-headline" data-finale={isFinale}>
      <span className="hc-sr">Your healthcare, connected.</span>
      {isFinale ? (
        <span className="hc-headline-finale" aria-hidden="true">
          Healthcare,
          <br />
          <em>finally</em> connected.
        </span>
      ) : (
        <span aria-hidden="true">
          Your
          <br />
          <span className="hc-rotating-word-frame">
            <span className="hc-rotating-word" key={CONNECTED_WORDS[sequenceIndex]}>
              {CONNECTED_WORDS[sequenceIndex]},
            </span>
          </span>
          <br />
          connected.
        </span>
      )}
    </h1>
  );
}