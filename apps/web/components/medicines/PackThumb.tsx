"use client";

import { useState } from "react";

/** Product photo with a deterministic fallback for missing bucket objects. */
export function PackThumb({
  brand,
  image,
  size = "md"
}: {
  brand: string;
  image?: string | null;
  size?: "md" | "result" | "lg" | "xl";
}) {
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const hasImage = Boolean(image && failedImage !== image);
  const sizeClass = size === "md" ? "" : ` hc-pack-${size}`;
  const stateClass = hasImage ? " hc-pack-image" : " hc-pack-fallback";
  const className = `hc-pack${sizeClass}${stateClass}`;

  if (image && hasImage) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <span className={className}>
        <img
          src={image}
          alt={`${brand} product packaging`}
          loading="lazy"
          decoding="async"
          onError={() => setFailedImage(image)}
        />
      </span>
    );
  }

  const firstLetter = brand.trim().charAt(0).toLocaleUpperCase() || "?";

  return (
    <span className={className} aria-label={`${brand} image unavailable`} role="img">
      <span>{firstLetter}</span>
    </span>
  );
}
