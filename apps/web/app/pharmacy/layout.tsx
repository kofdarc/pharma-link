import { ProtectedLayout } from "@/components/layout/ProtectedLayout";

export default function PharmacyLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedLayout roles={["PHARMACY_OWNER", "PHARMACY_STAFF"]} mode="pharmacy">
      {children}
    </ProtectedLayout>
  );
}

