export function ProductThumb({ src, alt }: { src?: string | null; alt: string }) {
  if (!src) {
    return (
      <div className="product-thumb product-thumb-placeholder" aria-hidden="true">
        No photo
      </div>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="product-thumb" src={src} alt={alt} loading="lazy" />;
}
