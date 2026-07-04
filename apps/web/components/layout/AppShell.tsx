"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api-client";
import { ADMIN_NAV, PHARMACY_NAV } from "@/lib/constants";
import type { User } from "@/types/api";

export function AppShell({
  user,
  mode,
  children
}: {
  user: User;
  mode: "pharmacy" | "admin";
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const nav = mode === "admin" ? ADMIN_NAV : PHARMACY_NAV;

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
            <strong>{mode === "admin" ? "Platform Admin" : user.pharmacy_detail?.name || "Pharmacy"}</strong>
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

