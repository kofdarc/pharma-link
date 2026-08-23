"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api-client";
import { ADMIN_NAV, DOCTOR_NAV, PHARMACY_NAV, SHOP_NAV } from "@/lib/constants";
import { useTranslations } from "@/lib/i18n/context";
import type { User } from "@/types/api";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { BrandMark } from "@/components/ui/BrandMark";

export type ShellMode = "pharmacy" | "admin" | "doctor" | "shop" | "driver";

const NAV_BY_MODE: Record<ShellMode, readonly (readonly [string, string])[]> = {
  pharmacy: PHARMACY_NAV,
  admin: ADMIN_NAV,
  doctor: DOCTOR_NAV,
  shop: SHOP_NAV,
  driver: [["My route", "/driver"]]
};

const NAV_TRANSLATION_KEYS: Record<string, string> = {
  "/shop": "nav.findMedicine",
  "/shop/orders": "nav.myOrders",
  "/shop/prescriptions": "nav.myPrescriptions",
  "/shop/refills": "nav.repeatRefills",
  "/shop/addresses": "nav.addresses",
  "/shop/insurance": "nav.insurance",
  "/pharmacy/dashboard": "nav.dashboard",
  "/pharmacy/analytics": "nav.analytics",
  "/pharmacy/orders": "nav.onlineOrders",
  "/pharmacy/inventory": "nav.inventory",
  "/pharmacy/clients": "nav.clients",
  "/pharmacy/imports": "nav.imports",
  "/pharmacy/sales": "nav.sales",
  "/pharmacy/prescriptions": "nav.prescriptions",
  "/pharmacy/scan": "nav.scanQrScript",
  "/pharmacy/connect": "nav.connectSoftware",
  "/pharmacy/billing": "nav.billing",
  "/pharmacy/insurance-claims": "nav.insuranceClaims",
  "/pharmacy/settings": "nav.settings",
  "/pharmacy/staff": "nav.staff",
  "/admin": "nav.admin",
  "/admin/dispatch": "nav.dispatchBoard",
  "/admin/pharmacies": "nav.pharmacies",
  "/admin/pharmacy-applications": "nav.pharmacyApplications",
  "/admin/billing": "nav.billing",
  "/admin/insurance": "nav.insurance",
  "/admin/medicines": "nav.medicines",
  "/admin/users": "nav.users",
  "/admin/imports": "nav.imports",
  "/admin/audit-logs": "nav.auditLogs",
  "/doctor/prescriptions": "nav.prescriptions",
  "/doctor/prescriptions/new": "nav.writeAPrescription",
  "/doctor/patients": "nav.patients",
  "/doctor/profile": "nav.profile",
  "/driver": "nav.myRoute"
};

function contextLabel(mode: ShellMode, user: User, t: (key: string) => string): string {
  if (mode === "admin") return t("shell.platformAdmin");
  if (mode === "pharmacy") return user.pharmacy_detail?.name || t("shell.pharmacy");
  if (mode === "doctor") return `${t("shell.doctorPrefix")} ${user.first_name} ${user.last_name}`.trim();
  if (mode === "driver") return t("shell.driverConsole");
  return "HealthConnect";
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
  const t = useTranslations();
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
          <BrandMark />
          <span>HealthConnect</span>
        </Link>
        <nav>
          {nav.map(([label, href]) => (
            <Link key={href} href={href} className={pathname === href ? "active" : ""}>
              {NAV_TRANSLATION_KEYS[href] ? t(NAV_TRANSLATION_KEYS[href]) : label}
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
              aria-label={navOpen ? t("shell.closeMenu") : t("shell.openMenu")}
              aria-expanded={navOpen}
              onClick={() => setNavOpen((open) => !open)}
            >
              <span />
              <span />
              <span />
            </button>
            <div>
              <strong>{contextLabel(mode, user, t)}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <div className="actions">
            <LanguageSwitcher />
            <button
              className="button button-secondary"
              onClick={() => {
                clearToken();
                router.push("/login");
              }}
            >
              {t("shell.logout")}
            </button>
          </div>
        </header>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
