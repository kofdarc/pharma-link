import type { Metadata } from "next";
import { DemoStage } from "./DemoStage";
import "./demo.css";

export const metadata: Metadata = {
  title: "Watch the demo",
  description:
    "Two minutes: a physician issues a prescription, a pharmacy dispenses it, and a patient gets it delivered — HealthConnect, finally connected.",
  alternates: { canonical: "https://www.healthconnect.dev/demo" },
  openGraph: {
    title: "HealthConnect — the two-minute demo",
    description:
      "One walkthrough across physician, pharmacy, and patient. No slides.",
    url: "https://www.healthconnect.dev/demo",
    type: "video.other"
  }
};

export default function DemoPage() {
  return <DemoStage />;
}
