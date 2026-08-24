import Link from "next/link";
import { Icon } from "@/components/ui/Icon";

/**
 * Split composition for the auth pages: form on one side, product on the other.
 *
 * The aside is HealthConnect's own interface rather than a photograph — the
 * thing you are signing in to, shown at the moment you decide to.
 */
export function AuthLayout({
  children,
  quote,
  points,
  visual
}: {
  children: React.ReactNode;
  quote: string;
  points: string[];
  visual?: React.ReactNode;
}) {
  return (
    <div className="hc hc-auth">
      <div className="hc-auth-main">
        <Link href="/" className="hc-brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-mark.png" alt="" />
          <span>HealthConnect</span>
        </Link>
        <div className="hc-auth-body">
          <div className="hc-auth-card">{children}</div>
        </div>
      </div>

      <aside className="hc-auth-aside">
        <blockquote>{quote}</blockquote>
        {visual ? <div className="hc-auth-visual">{visual}</div> : null}
        <ul className="hc-auth-points">
          {points.map((point) => (
            <li key={point}>
              <Icon name="check" size={16} />
              {point}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
