import { ProtectedLayout } from "@/components/layout/ProtectedLayout";

export default function ShopLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedLayout roles={["CUSTOMER"]} mode="shop">
      {children}
    </ProtectedLayout>
  );
}
