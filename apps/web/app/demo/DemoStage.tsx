"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrandLogo } from "@/components/ui/BrandMark";
import { Icon } from "@/components/ui/Icon";

// The recorded walkthrough lives on the demo media CDN (S3 + CloudFront,
// media.healthconnect.dev) as three progressive MP4 renditions. Override the
// base per environment if it ever moves.
const MEDIA_BASE =
  process.env.NEXT_PUBLIC_DEMO_MEDIA_BASE ?? "https://media.healthconnect.dev";

type QualityId = "1080p" | "720p" | "480p";

const QUALITIES: { id: QualityId; label: string; url: string }[] = [
  { id: "1080p", label: "1080p", url: `${MEDIA_BASE}/demo-1080p.mp4` },
  { id: "720p", label: "720p", url: `${MEDIA_BASE}/demo-720p.mp4` },
  { id: "480p", label: "480p", url: `${MEDIA_BASE}/demo-480p.mp4` }
];

const DEMO_POSTER_URL =
  process.env.NEXT_PUBLIC_DEMO_POSTER_URL ?? `${MEDIA_BASE}/demo-poster.jpg`;

// Best guess before the viewer says otherwise. Uses the Network Information API
// where it exists (Chrome/Edge/Android); Safari and Firefox don't expose it, so
// they fall through to 720p.
function pickAutoQuality(): QualityId {
  if (typeof navigator === "undefined") return "720p";
  const conn = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string; downlink?: number };
    }
  ).connection;
  if (!conn) return "720p";
  if (conn.saveData) return "480p";
  if (conn.effectiveType && conn.effectiveType !== "4g") return "480p";
  if (typeof conn.downlink === "number") {
    if (conn.downlink >= 6) return "1080p";
    if (conn.downlink < 1.8) return "480p";
  }
  return "720p";
}

export function DemoStage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);
  // "auto" defers to the connection-derived pick; an explicit id pins it.
  const [mode, setMode] = useState<"auto" | QualityId>("auto");
  // Starts at 720p to match SSR, then resolves against the real connection on
  // the client so hydration stays clean.
  const [autoQuality, setAutoQuality] = useState<QualityId>("720p");
  // Stashed across a source swap so the viewer keeps their place.
  const resumeRef = useRef<{ at: number; play: boolean } | null>(null);

  useEffect(() => {
    setAutoQuality(pickAutoQuality());
  }, []);

  const activeId: QualityId = mode === "auto" ? autoQuality : mode;
  const activeUrl = QUALITIES.find((q) => q.id === activeId)!.url;

  const start = () => {
    setStarted(true);
    // Hand playback to the browser; if the source is missing or autoplay is
    // blocked, the native controls are already visible for the viewer.
    videoRef.current?.play().catch(() => undefined);
  };

  const changeQuality = (next: "auto" | QualityId) => {
    const video = videoRef.current;
    if (video && started) {
      resumeRef.current = {
        at: video.currentTime,
        play: !video.paused && !video.ended
      };
    }
    // Recompute the auto pick each time it's chosen — the connection may have
    // changed since the page loaded.
    if (next === "auto") setAutoQuality(pickAutoQuality());
    setMode(next);
  };

  // React swaps the <source> on `activeUrl` change, which reloads the element;
  // once metadata is back, drop the viewer where they were.
  const handleLoadedMetadata = () => {
    const resume = resumeRef.current;
    const video = videoRef.current;
    if (!resume || !video) return;
    resumeRef.current = null;
    if (resume.at) video.currentTime = resume.at;
    if (resume.play) video.play().catch(() => undefined);
  };

  return (
    <main className="demo-stage">
      <div className="demo-glow" aria-hidden="true" />

      <div className="demo-inner">
        <Link href="/" className="demo-brand" aria-label="HealthConnect home">
          <BrandLogo tone="on-dark" />
        </Link>

        <h1 className="demo-headline hc-display">
          See it <em>finally</em> connected.
        </h1>

        <div className={`demo-frame${started ? " is-playing" : ""}`}>
          <video
            key={activeUrl}
            ref={videoRef}
            className="demo-video"
            controls={started}
            playsInline
            preload="metadata"
            poster={DEMO_POSTER_URL}
            onLoadedMetadata={handleLoadedMetadata}
          >
            <source src={activeUrl} type="video/mp4" />
          </video>

          {started ? (
            <label className="demo-quality">
              <span className="demo-quality-label">Quality</span>
              <select
                className="demo-quality-select"
                value={mode}
                onChange={(event) =>
                  changeQuality(event.target.value as "auto" | QualityId)
                }
              >
                <option value="auto">Auto ({autoQuality})</option>
                {QUALITIES.map((quality) => (
                  <option key={quality.id} value={quality.id}>
                    {quality.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

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
