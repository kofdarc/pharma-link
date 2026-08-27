import { PatientGuard } from "@/components/site/PatientGuard";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <PatientGuard>{children}</PatientGuard>;
}
