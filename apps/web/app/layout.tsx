import type { Metadata, Viewport } from "next";
import { Fraunces, Inter } from "next/font/google";
import "./globals.css";
import "./poc.css";
import "./patient.css";
import "./patient-ui.css";
import "./patient-app.css";
import "./receipt.css";
import { RegisterServiceWorker } from "@/components/pwa/RegisterServiceWorker";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { I18nProvider } from "@/lib/i18n/context";
import { LocalizedContent } from "@/components/i18n/LocalizedContent";
import { AssistantWidget } from "@/components/assistant/AssistantWidget";

// Inter carries the whole product; Fraunces is display-only (hero and section
// headlines on the patient-facing pages). Two families, one job each.
const sans = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans"
});

const display = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display"
});

export const metadata: Metadata = {
  title: {
    default: "HealthConnect",
    template: "%s · HealthConnect"
  },
  description: "Find medication across connected pharmacies, handle prescription requirements, and get what you need delivered.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "HealthConnect"
  },
  icons: {
    shortcut: [{ url: "/brand/favicon-48.png", sizes: "48x48", type: "image/png" }],
    icon: [
      { url: "/brand/favicon-48.png", sizes: "48x48", type: "image/png" }
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#00bf63"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body>
        <I18nProvider>
          <LocalizedContent>
            {children}
            <AssistantWidget />
            <RegisterServiceWorker />
            <InstallPrompt />
          </LocalizedContent>
        </I18nProvider>
      </body>
    </html>
  );
}
