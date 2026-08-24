import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./poc.css";
import { RegisterServiceWorker } from "@/components/pwa/RegisterServiceWorker";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { I18nProvider } from "@/lib/i18n/context";

export const metadata: Metadata = {
  title: "HealthConnect",
  description: "Pharmacy medication availability and inventory management",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "HealthConnect"
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" }
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#087f83"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          {children}
          <RegisterServiceWorker />
          <InstallPrompt />
        </I18nProvider>
      </body>
    </html>
  );
}

