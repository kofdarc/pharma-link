"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { useOptionalUser } from "@/lib/auth";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/about", label: "About" },
  { href: "/search", label: "Search medicines" }
];

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // Resolves after mount. Signed-out is the right first paint for a public
  // page, so only the two trailing actions change once we know otherwise.
  const user = useOptionalUser();

  // Route changes should not leave the panel hanging open behind the new page.
  useEffect(() => setOpen(false), [pathname]);

  const current = (href: string) => (pathname === href ? "page" : undefined);

  return (
    <header className="hc-header">
      <div className="hc-wrap hc-header-inner">
        <Link href="/" className="hc-brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-mark.png" alt="" />
          <span>HealthConnect</span>
        </Link>

        <nav className="hc-nav" aria-label="Main">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} aria-current={current(link.href)}>
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hc-header-actions">
          {user ? (
            <Link href="/home" className="hc-btn hc-btn-secondary hc-btn-sm">
              <Icon name="home" size={16} />
              My HealthConnect
            </Link>
          ) : (
            <>
              <Link href="/login" className="hc-btn hc-btn-quiet hc-btn-sm hc-desktop-only">
                Sign in
              </Link>
              <Link href="/register" className="hc-btn hc-btn-primary hc-btn-sm">
                Get started
              </Link>
            </>
          )}
          <button
            type="button"
            className="hc-burger"
            aria-expanded={open}
            aria-controls="hc-mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            <Icon name={open ? "close" : "menu"} size={20} />
          </button>
        </div>
      </div>

      {open ? (
        <div className="hc-mobile-panel" id="hc-mobile-nav">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} aria-current={current(link.href)}>
              {link.label}
            </Link>
          ))}
          <div className="hc-mobile-cta">
            {user ? (
              <Link href="/home" className="hc-btn hc-btn-primary hc-btn-block">
                Go to my HealthConnect
              </Link>
            ) : (
              <>
                <Link href="/login" className="hc-btn hc-btn-secondary hc-btn-block">
                  Sign in
                </Link>
                <Link href="/register" className="hc-btn hc-btn-primary hc-btn-block">
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      ) : null}
    </header>
  );
}
