/**
 * The basket is open to everyone.
 *
 * A visitor can search, add medications and see how the basket could be filled
 * without an account; the sign-in gate is at `/checkout` (see its layout), the
 * first point where an order, an address and a prescription are actually
 * committed. So this segment deliberately has no `PatientGuard`.
 */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
