"use client";

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
  return "MediSync";
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>MediSync</span>
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
          <div>
            <strong>{contextLabel(mode, user)}</strong>
            <span>{user.email}</span>
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
