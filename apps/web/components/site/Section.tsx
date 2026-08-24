import Link from "next/link";
import { Icon } from "@/components/ui/Icon";

export function SectionHeading({
  eyebrow,
  title,
  lead,
  align = "start",
  id
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  align?: "start" | "center";
  id?: string;
}) {
  return (
    <div className={`hc-heading${align === "center" ? " hc-heading-center" : ""}`}>
      {eyebrow ? <p className="hc-eyebrow">{eyebrow}</p> : null}
      <h2 className="hc-h2" id={id}>
        {title}
      </h2>
      {lead ? <p className="hc-lead">{lead}</p> : null}
    </div>
  );
}

export function ArrowLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="hc-textlink">
      {children}
      <Icon name="arrowRight" size={16} />
    </Link>
  );
}

export function CtaSection({
  title,
  lead,
  primary,
  secondary
}: {
  title: string;
  lead: string;
  primary: { href: string; label: string };
  secondary: { href: string; label: string };
}) {
  return (
    <section className="hc-section">
      <div className="hc-wrap">
        <div className="hc-cta">
          <h2 className="hc-h2">{title}</h2>
          <p className="hc-lead">{lead}</p>
          <div className="hc-actions">
            <Link href={primary.href} className="hc-btn hc-btn-onbrand hc-btn-lg">
              <Icon name="search" size={18} />
              {primary.label}
            </Link>
            <Link href={secondary.href} className="hc-btn hc-btn-ghost-onbrand hc-btn-lg">
              {secondary.label}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
