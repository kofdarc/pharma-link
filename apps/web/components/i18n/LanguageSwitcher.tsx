"use client";

import { LOCALES, LOCALE_LABELS, useLocale } from "@/lib/i18n/context";

export function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();

  return (
    <select
      className="language-switcher"
      value={locale}
      onChange={(event) => setLocale(event.target.value as (typeof LOCALES)[number])}
      aria-label="Language"
    >
      {LOCALES.map((entry) => (
        <option key={entry} value={entry}>
          {LOCALE_LABELS[entry]}
        </option>
      ))}
    </select>
  );
}
