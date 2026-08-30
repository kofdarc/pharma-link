"use client";

import Link from "next/link";
import { BrandLogo } from "@/components/ui/BrandMark";
import { useTranslations } from "@/lib/i18n/context";

/**
 * Links that have no route yet render as plain text, not as links to nowhere.
 * Building placeholder Help/Contact/Privacy/Terms pages was out of scope for
 * this slice, and a dead <a> is worse than an honest label.
 */
type FooterLink = { labelKey: string; href?: string };

const GROUPS: { id: string; titleKey: string; links: FooterLink[] }[] = [
  {
    id: "healthconnect",
    titleKey: "publicFooter.healthConnect",
    links: [
      { labelKey: "publicFooter.about", href: "/about" },
      { labelKey: "publicFooter.howItWorks", href: "/how-it-works" }
    ]
  },
  {
    id: "patients",
    titleKey: "publicFooter.patients",
    links: [
      { labelKey: "publicFooter.searchMedicines", href: "/search" },
      { labelKey: "common.signIn", href: "/login" },
      { labelKey: "publicFooter.createAccount", href: "/register" }
    ]
  },
  {
    id: "professionals",
    titleKey: "publicFooter.professionals",
    links: [
      { labelKey: "publicFooter.pharmacies", href: "/pharmacy-signup" },
      { labelKey: "publicFooter.physicians", href: "/activate" },
      { labelKey: "publicFooter.dispensePrescription", href: "/rx" }
    ]
  },
  {
    id: "support-legal",
    titleKey: "publicFooter.supportLegal",
    links: [
      { labelKey: "publicFooter.help" },
      { labelKey: "publicFooter.contact" },
      { labelKey: "publicFooter.privacy" },
      { labelKey: "publicFooter.terms" }
    ]
  }
];

export function SiteFooter() {
  const t = useTranslations();

  return (
    <footer className="hc-footer">
      <div className="hc-wrap">
        <div className="hc-footer-grid">
          <div className="hc-footer-brandcol">
            <Link href="/" className="hc-brand">
              <BrandLogo />
            </Link>
            <p className="hc-small">
              {t("publicFooter.description")}
            </p>
          </div>

          {GROUPS.map((group) => (
            <nav key={group.id} aria-labelledby={`footer-${group.id}`}>
              <h2 id={`footer-${group.id}`}>{t(group.titleKey)}</h2>
              <ul>
                {group.links.map((link) => (
                  <li key={link.labelKey}>
                    {link.href ? <Link href={link.href}>{t(link.labelKey)}</Link> : <span>{t(link.labelKey)}</span>}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="hc-footer-base">
          <p className="hc-small">© {new Date().getFullYear()} {t("publicFooter.projectCredit")}</p>
          <p className="hc-small">{t("publicFooter.medicalDisclaimer")}</p>
        </div>
      </div>
    </footer>
  );
}
