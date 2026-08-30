"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { BrandLogo } from "@/components/ui/BrandMark";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { useOptionalUser } from "@/lib/auth";
import { useBasket } from "@/lib/basket";
import { useTranslations } from "@/lib/i18n/context";

const LINKS = [
  { href: "/", labelKey: "publicHeader.home" },
  { href: "/how-it-works", labelKey: "publicHeader.howItWorks" },
  { href: "/about", labelKey: "publicHeader.about" },
  { href: "/search", labelKey: "publicHeader.searchMedicines" }
];

export function SiteHeader() {
  const t = useTranslations();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // Resolves after mount. Signed-out is the right first paint for a public
  // page, so only the two trailing actions change once we know otherwise.
  const user = useOptionalUser();
  const { count, ready } = useBasket();

  // Route changes should not leave the panel hanging open behind the new page.
  useEffect(() => setOpen(false), [pathname]);

  const current = (href: string) => (pathname === href ? "page" : undefined);

  return (
    <header className="hc-header">
      <div className="hc-wrap hc-header-inner">
        <Link href="/" className="hc-brand">
          <BrandLogo />
        </Link>

        <nav className="hc-nav" aria-label={t("publicHeader.mainNavigation")}>
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} aria-current={current(link.href)}>
              {t(link.labelKey)}
            </Link>
          ))}
        </nav>

        <div className="hc-header-actions">
          <LanguageSwitcher className="hc-header-language hc-desktop-language" />
          <Link
            href="/cart"
            className="hc-cartbtn"
            aria-current={current("/cart")}
            aria-label={
              ready && count > 0
                ? t("publicHeader.basketWithCount", { count })
                : t("publicHeader.basket")
            }
          >
            <Icon name="cart" size={19} />
            {ready && count > 0 ? (
              <span className="hc-cartbtn-count hc-num" aria-hidden="true">
                {count > 9 ? "9+" : count}
              </span>
            ) : null}
          </Link>
          {user ? (
            <Link href="/home" className="hc-btn hc-btn-secondary hc-btn-sm">
              <Icon name="home" size={16} />
              {t("publicHeader.myHealthConnect")}
            </Link>
          ) : (
            <>
              <Link href="/login" className="hc-btn hc-btn-quiet hc-btn-sm hc-desktop-only">
                {t("common.signIn")}
              </Link>
              <Link href="/register" className="hc-btn hc-btn-primary hc-btn-sm">
                {t("publicHeader.getStarted")}
              </Link>
            </>
          )}
          <button
            type="button"
            className="hc-burger"
            aria-expanded={open}
            aria-controls="hc-mobile-nav"
            aria-label={open ? t("publicHeader.closeMenu") : t("publicHeader.openMenu")}
            onClick={() => setOpen((value) => !value)}
          >
            <Icon name={open ? "close" : "menu"} size={20} />
          </button>
        </div>
      </div>

      {open ? (
        <div className="hc-mobile-panel" id="hc-mobile-nav">
          <div className="hc-mobile-language">
            <LanguageSwitcher className="hc-header-language" />
          </div>
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} aria-current={current(link.href)}>
              {t(link.labelKey)}
            </Link>
          ))}
          <div className="hc-mobile-cta">
            {user ? (
              <Link href="/home" className="hc-btn hc-btn-primary hc-btn-block">
                {t("publicHeader.goToMyHealthConnect")}
              </Link>
            ) : (
              <>
                <Link href="/login" className="hc-btn hc-btn-secondary hc-btn-block">
                  {t("common.signIn")}
                </Link>
                <Link href="/register" className="hc-btn hc-btn-primary hc-btn-block">
                  {t("publicHeader.getStarted")}
                </Link>
              </>
            )}
          </div>
        </div>
      ) : null}
    </header>
  );
}
