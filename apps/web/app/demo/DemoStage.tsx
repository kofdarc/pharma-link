"use client";

import Link from "next/link";
import { BrandLogo } from "@/components/ui/BrandMark";
import { Icon } from "@/components/ui/Icon";

export function DemoStage() {
  return (
    <main className="demo-stage">
      <div className="demo-glow" aria-hidden="true" />

      <div className="demo-inner">
        <Link href="/" className="demo-brand" aria-label="HealthConnect home">
          <BrandLogo tone="on-dark" />
        </Link>

        <p className="demo-eyebrow">Two-minute demo</p>
        <h1 className="demo-headline hc-display">
          See it <em>finally</em> connected.
        </h1>
        <div className="demo-frame">
          <p className="demo-removed" role="alert">
            This video has been removed due to a music copyright claim
          </p>
        </div>

        <div className="demo-actions">
          <Link href="/login" className="hc-btn hc-btn-primary hc-btn-lg">
            Try the live demo
          </Link>
          <Link href="/how-it-works" className="demo-secondary">
            How it works
            <Icon name="arrowRight" size={16} />
          </Link>
        </div>
      </div>
    </main>
  );
}
