import type { Metadata } from "next";
import "./globals.css";
import "./poc.css";

export const metadata: Metadata = {
  title: "MediSync",
  description: "Pharmacy medication availability and inventory management"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

