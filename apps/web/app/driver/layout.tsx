import { ProtectedLayout } from "@/components/layout/ProtectedLayout";

export default function DriverLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedLayout roles={["DRIVER"]} mode="driver">
      {children}
    </ProtectedLayout>
  );
}
