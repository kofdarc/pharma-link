import Image from "next/image";

type BrandTone = "primary" | "on-dark";

export function BrandMark({ tone = "primary" }: { tone?: BrandTone }) {
  return (
    <Image
      src={`/brand/mark-${tone}.webp`}
      alt=""
      width={220}
      height={270}
      className="brand-mark"
    />
  );
}

export function BrandLogo({ tone = "primary" }: { tone?: BrandTone }) {
  if (tone === "primary") {
    return (
      <Image
        src="/brand/logo-primary.webp"
        alt="HealthConnect"
        width={926}
        height={243}
        className="brand-logo-image"
        priority
      />
    );
  }

  return (
    <span className="brand-logo" role="img" aria-label="HealthConnect">
      <BrandMark tone={tone} />
      <span className="brand-wordmark" aria-hidden="true">
        <span className="brand-wordmark-health-on-dark">Health</span>
        <span className="brand-wordmark-connect">Connect</span>
      </span>
    </span>
  );
}
