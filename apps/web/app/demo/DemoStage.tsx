"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { BrandLogo } from "@/components/ui/BrandMark";
import { Icon } from "@/components/ui/Icon";

// The recorded walkthrough lives on the demo media CDN (S3 + CloudFront,
// media.healthconnect.dev). Override per environment if it ever moves.
const DEMO_VIDEO_URL =
  process.env.NEXT_PUBLIC_DEMO_VIDEO_URL ?? "https://media.healthconnect.dev/demo.mp4";
// Optional still frame shown before playback. Left unset until the poster is
// produced — the play overlay covers the frame in the meantime.
const DEMO_POSTER_URL = process.env.NEXT_PUBLIC_DEMO_POSTER_URL;

export function DemoStage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);

  const start = () => {
    setStarted(true);
    // Hand playback to the browser; if the source is missing or autoplay is
    // blocked, the native controls are already visible for the viewer.
    videoRef.current?.play().catch(() => undefined);
  };

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
        <p className="demo-lead">
          One unbroken walkthrough — a physician issues a prescription, a pharmacy
          verifies and dispenses it, and a patient gets it delivered. No slides.
        </p>

        <div className={`demo-frame${started ? " is-playing" : ""}`}>
          <video
            ref={videoRef}
            className="demo-video"
            controls={started}
            playsInline
            preload="metadata"
            poster={DEMO_POSTER_URL}
          >
            <source src={DEMO_VIDEO_URL} type="video/mp4" />
          </video>

          {!started ? (
            <button type="button" className="demo-play" onClick={start}>
              <span className="demo-play-ring">
                <Icon name="play" size={30} />
              </span>
              <span className="demo-play-label">Watch the 2-minute demo</span>
            </button>
          ) : null}
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
