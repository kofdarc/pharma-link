"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "@/lib/i18n/context";

const CONNECTED_WORD_KEYS = ["medications", "prescriptions", "physicians", "pharmacies"] as const;
const FINALE_INDEX = CONNECTED_WORD_KEYS.length;
const WORD_DURATION_MS = 2400;
const FINALE_DURATION_MS = 4600;

export function ConnectedHeadline() {
  const t = useTranslations();
  const [sequenceIndex, setSequenceIndex] = useState(0);
  const isFinale = sequenceIndex === FINALE_INDEX;

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const timeout = window.setTimeout(
      () => setSequenceIndex((current) => (current + 1) % (CONNECTED_WORD_KEYS.length + 1)),
      isFinale ? FINALE_DURATION_MS : WORD_DURATION_MS
    );

    return () => window.clearTimeout(timeout);
  }, [isFinale, sequenceIndex]);

  return (
    <h1 className="hc-display hc-connected-headline" data-finale={isFinale}>
      <span className="hc-sr">{t("marketingHero.headlineAccessible")}</span>
      {isFinale ? (
        <span className="hc-headline-finale" aria-hidden="true">
          {t("marketingHero.healthcare")},
          <br />
          <em>{t("marketingHero.finally")}</em> {t("marketingHero.connected")}.
        </span>
      ) : (
        <span aria-hidden="true">
          {t("marketingHero.your")}
          <br />
          <span className="hc-rotating-word-frame">
            <span className="hc-rotating-word" key={CONNECTED_WORD_KEYS[sequenceIndex]}>
              {t(`marketingHero.${CONNECTED_WORD_KEYS[sequenceIndex]}`)},
            </span>
          </span>
          <br />
          {t("marketingHero.connected")}.
        </span>
      )}
    </h1>
  );
}
