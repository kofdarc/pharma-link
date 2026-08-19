"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api-client";
import { ADMIN_NAV, DOCTOR_NAV, PHARMACY_NAV, SHOP_NAV } from "@/lib/constants";
import type { User } from "@/types/api";

export type ShellMode = "pharmacy" | "admin" | "doctor" | "shop" | "driver";

const NAV_BY_MODE: Record<ShellMode, readonly (readonly [string, string])[]> = {
  pharmacy: PHARMACY_NAV,
  admin: ADMIN_NAV,
  doctor: DOCTOR_NAV,
  shop: SHOP_NAV,
  driver: [["My route", "/driver"]]
};

function contextLabel(mode: ShellMode, user: User): string {
  if (mode === "admin") return "Platform Admin";
  if (mode === "pharmacy") return user.pharmacy_detail?.name || "Pharmacy";
  if (mode === "doctor") return `Dr. ${user.first_name} ${user.last_name}`.trim();
  if (mode === "driver") return "Driver console";
  return "PharmaLink";
}

export function AppShell({
  user,
  mode,
  children
}: {
  user: User;
  mode: ShellMode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const nav = NAV_BY_MODE[mode];
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  return (
    <div className="app-shell">
      <button
        type="button"
        className="nav-backdrop"
        aria-hidden={!navOpen}
        data-open={navOpen}
        onClick={() => setNavOpen(false)}
        tabIndex={-1}
      />
      <aside className="sidebar" data-open={navOpen}>
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>PharmaLink</span>
        </Link>
        <nav>
          {nav.map(([label, href]) => (
            <Link key={href} href={href} className={pathname === href ? "active" : ""}>
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-start">
            <button
              type="button"
              className="nav-toggle"
              aria-label={navOpen ? "Close menu" : "Open menu"}
              aria-expanded={navOpen}
              onClick={() => setNavOpen((open) => !open)}
            >
              <span />
              <span />
              <span />
            </button>
            <div>
              <strong>{contextLabel(mode, user)}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <button
            className="button button-secondary"
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            Logout
          </button>
        </header>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
