"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { BrandLogo } from "@/components/ui/BrandMark";
import { ToastProvider } from "@/components/patient/Toast";
import { useMaybePatientUser } from "@/components/site/PatientGuard";
import { useBasket } from "@/lib/basket";
import { signOut } from "@/lib/auth";
import { notificationCountForHref, useNotifications } from "@/lib/notifications/useNotifications";
import type { User } from "@/types/api";

/**
 * Chrome for the signed-in patient area.
 *
 * Patient destinations use the same sidebar pattern as the clinical and pharmacy
 * workspaces. The basket remains a header action because it is a checkout step,
 * not a section patients return to for ongoing work.
 */
const TABS = [
  { href: "/home", label: "Home" },
  { href: "/search", label: "Find medicine" },
  { href: "/prescriptions", label: "Prescriptions" },
  { href: "/orders", label: "Orders" },
  { href: "/refills", label: "Repeat refills" },
  { href: "/shop/insurance", label: "Insurance" },
  { href: "/account", label: "Account" }
];

/**
 * `user` is only passed on pages outside `PatientGuard` - the public search
 * page, which wears this chrome when a patient happens to be signed in. Inside
 * the patient area the guard has already resolved the user, so the shell reads
 * it from there rather than every page threading it down.
 */
export function PatientShell({ children, user }: { children: React.ReactNode; user?: User | null }) {
  return <ToastProvider><PatientShellContent user={user}>{children}</PatientShellContent></ToastProvider>;
}

function PatientShellContent({ children, user }: { children: React.ReactNode; user?: User | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const { count, ready } = useBasket();
  const contextUser = useMaybePatientUser();
  const shellUser = user ?? contextUser;
  const initials = initialsFor(shellUser?.first_name, shellUser?.last_name);
  const [navOpen, setNavOpen] = useState(false);
  const { items } = useNotifications(shellUser?.id);

  useEffect(() => setNavOpen(false), [pathname]);

  // `/cart` and `/checkout` belong to the basket action, so no tab claims them.
  const current = (href: string) => (pathname === href || pathname.startsWith(`${href}/`) ? "page" : undefined);

  return (
      <div className="hc hc-app app-shell">
        <button type="button" className="nav-backdrop" aria-hidden={!navOpen} data-open={navOpen} onClick={() => setNavOpen(false)} tabIndex={-1} />
        <aside className="sidebar" data-open={navOpen}>
          <Link href="/home" className="brand"><BrandLogo tone="on-dark" /></Link>
          <nav aria-label="Patient">
            {TABS.map((tab) => {
              const updates = notificationCountForHref(items, tab.href);
              return (
                <Link key={tab.href} href={tab.href} className={current(tab.href) ? "active" : ""}>
                  <span>{tab.label}</span>
                  {updates > 0 ? <span className="nav-count" aria-label={`${updates} updates`}>{updates > 99 ? "99+" : updates}</span> : null}
                </Link>
              );
            })}
          </nav>
        </aside>
        <div className="main-panel">
          <header className="topbar">
            <div className="topbar-start">
              <button type="button" className="nav-toggle" aria-label={navOpen ? "Close menu" : "Open menu"} aria-expanded={navOpen} onClick={() => setNavOpen((open) => !open)}><span /><span /><span /></button>
              <div><strong>HealthConnect</strong><span>{shellUser?.email}</span></div>
            </div>
            <div className="actions">
              <Link
                href="/cart"
                className="hc-cartbtn"
                aria-current={current("/cart")}
                aria-label={ready && count > 0 ? `Basket, ${count} in it` : "Basket"}
              >
                <Icon name="cart" size={19} />
                {ready && count > 0 ? (
                  <span className="hc-cartbtn-count hc-num" aria-hidden="true">
                    {count > 9 ? "9+" : count}
                  </span>
                ) : null}
              </Link>
              <Link href="/account" className="hc-avatar" aria-label="Account">
                <span aria-hidden="true">{initials}</span>
              </Link>
              <button className="button button-secondary" onClick={() => { signOut(); router.push("/login"); }}>Log out</button>
            </div>
          </header>
          <main className="hc-main">{children}</main>
        </div>
      </div>
  );
}

/**
 * The initials shown in the header.
 *
 * Falls back to the first letter of whatever name is known rather than a
 * generic avatar glyph, and never renders an empty circle.
 */
export function initialsFor(firstName?: string | null, lastName?: string | null): string {
  const first = (firstName ?? "").trim();
  const last = (lastName ?? "").trim();
  return `${first[0] ?? "H"}${last[0] ?? ""}`.toUpperCase();
}
