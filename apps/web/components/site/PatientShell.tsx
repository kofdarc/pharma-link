"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/Icon";
import { BrandLogo } from "@/components/ui/BrandMark";
import { ToastProvider } from "@/components/patient/Toast";
import { useMaybePatientUser } from "@/components/site/PatientGuard";
import { useBasket } from "@/lib/basket";
import type { User } from "@/types/api";

/**
 * Chrome for the signed-in patient area.
 *
 * Five destinations, and no more. The basket is an action rather than a
 * section: it is somewhere the patient passes through on the way to an order,
 * not somewhere they go to spend time, so it sits in the header with a count
 * and stays out of the tab bar where thumb reach is scarce.
 */
const TABS: { href: string; label: string; short: string; icon: IconName }[] = [
  { href: "/home", label: "Home", short: "Home", icon: "home" },
  { href: "/search", label: "Search", short: "Search", icon: "search" },
  { href: "/prescriptions", label: "Prescriptions", short: "Rx", icon: "rx" },
  { href: "/orders", label: "Orders", short: "Orders", icon: "box" },
  { href: "/account", label: "Account", short: "Account", icon: "user" }
];

/**
 * `user` is only passed on pages outside `PatientGuard` - the public search
 * page, which wears this chrome when a patient happens to be signed in. Inside
 * the patient area the guard has already resolved the user, so the shell reads
 * it from there rather than every page threading it down.
 */
export function PatientShell({ children, user }: { children: React.ReactNode; user?: User | null }) {
  const pathname = usePathname();
  const { count, ready } = useBasket();
  const contextUser = useMaybePatientUser();
  const shellUser = user ?? contextUser;
  const initials = initialsFor(shellUser?.first_name, shellUser?.last_name);

  // `/cart` and `/checkout` belong to the basket action, so no tab claims them.
  const current = (href: string) => (pathname === href || pathname.startsWith(`${href}/`) ? "page" : undefined);

  return (
    <ToastProvider>
      <div className="hc hc-app">
        <header className="hc-appnav">
          <div className="hc-wrap hc-appnav-inner">
            <Link href="/home" className="hc-brand">
              <BrandLogo />
            </Link>

            <nav className="hc-appnav-links" aria-label="Patient">
              {TABS.map((tab) => (
                <Link key={tab.href} href={tab.href} aria-current={current(tab.href)}>
                  {tab.label}
                </Link>
              ))}
            </nav>

            <div className="hc-appnav-end">
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
            </div>
          </div>
        </header>

        <main className="hc-main">{children}</main>

        <nav className="hc-tabbar" aria-label="Patient sections">
          <ul>
            {TABS.map((tab) => (
              <li key={tab.href}>
                <Link href={tab.href} aria-current={current(tab.href)}>
                  <Icon name={tab.icon} size={21} />
                  {tab.short}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </ToastProvider>
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
