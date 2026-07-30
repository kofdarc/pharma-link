"use client";

import { AppShell, type ShellMode } from "./AppShell";
import { useRequireRole } from "@/lib/auth";
import type { UserRole } from "@/types/api";

export function ProtectedLayout({
  roles,
  mode,
  children
}: {
  roles: UserRole[];
  mode: ShellMode;
  children: React.ReactNode;
}) {
  const { user, loading } = useRequireRole(roles);

  if (loading || !user) {
    return (
      <div className="center-screen">
        <div className="skeleton-card" />
      </div>
    );
  }

  return (
    <AppShell user={user} mode={mode}>
      {children}
    </AppShell>
  );
}

