import Link from "next/link";
import { BrandLogo } from "@/components/ui/BrandMark";

/**
 * Links that have no route yet render as plain text, not as links to nowhere.
 * Building placeholder Help/Contact/Privacy/Terms pages was out of scope for
 * this slice, and a dead <a> is worse than an honest label.
 */
type FooterLink = { label: string; href?: string };

const GROUPS: { title: string; links: FooterLink[] }[] = [
  {
    title: "HealthConnect",
    links: [
      { label: "About", href: "/about" },
      { label: "How it works", href: "/how-it-works" }
    ]
  },
  {
    title: "Patients",
    links: [
      { label: "Search medicines", href: "/search" },
      { label: "Sign in", href: "/login" },
      { label: "Create an account", href: "/register" }
    ]
  },
  {
    title: "Professionals",
    links: [
      { label: "Pharmacies", href: "/pharmacy-signup" },
      { label: "Physicians", href: "/activate" },
      { label: "Dispense a prescription", href: "/rx" }
    ]
  },
  {
    title: "Support & legal",
    links: [{ label: "Help" }, { label: "Contact" }, { label: "Privacy" }, { label: "Terms" }]
  }
];

export function SiteFooter() {
  return (
    <footer className="hc-footer">
      <div className="hc-wrap">
        <div className="hc-footer-grid">
          <div className="hc-footer-brandcol">
            <Link href="/" className="hc-brand">
              <BrandLogo />
            </Link>
            <p className="hc-small">
              Medication search, secure prescriptions and delivery across connected pharmacies in Lebanon.
            </p>
          </div>

          {GROUPS.map((group) => (
            <nav key={group.title} aria-labelledby={`footer-${group.title.replace(/\W+/g, "-").toLowerCase()}`}>
              <h2 id={`footer-${group.title.replace(/\W+/g, "-").toLowerCase()}`}>{group.title}</h2>
              <ul>
                {group.links.map((link) => (
                  <li key={link.label}>
                    {link.href ? <Link href={link.href}>{link.label}</Link> : <span>{link.label}</span>}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="hc-footer-base">
          <p className="hc-small">© {new Date().getFullYear()} HealthConnect. A student project built at the American University of Beirut.</p>
          <p className="hc-small">HealthConnect does not provide medical advice.</p>
        </div>
      </div>
    </footer>
  );
}
