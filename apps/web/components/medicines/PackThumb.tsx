/**
 * Product imagery stand-in.
 *
 * Most catalogue records have no photograph, and generic pill photos would be
 * both misleading and worse-looking than nothing. A typographic tile keyed to
 * the brand name is honest, consistent, and gives every result the same visual
 * weight. A real image is used whenever the record has one.
 */
export function PackThumb({
  brand,
  image,
  size = "md"
}: {
  brand: string;
  image?: string | null;
  size?: "md" | "lg" | "xl";
}) {
  const className = `hc-pack${size === "lg" ? " hc-pack-lg" : ""}${size === "xl" ? " hc-pack-xl" : ""}`;

  if (image) {
    // eslint-disable-next-line @next/next/no-img-element
    return <span className={className}>{<img src={image} alt="" loading="lazy" />}</span>;
  }

  const initials = brand
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return (
    <span className={className} aria-hidden="true">
      {initials}
    </span>
  );
}
