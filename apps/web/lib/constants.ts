export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export const PHARMACY_NAV = [
  ["Dashboard", "/pharmacy/dashboard"],
  ["Analytics", "/pharmacy/analytics"],
  ["Online orders", "/pharmacy/orders"],
  ["Inventory", "/pharmacy/inventory"],
  ["Clients", "/pharmacy/clients"],
  ["Imports", "/pharmacy/imports"],
  ["Sales", "/pharmacy/sales"],
  ["Prescriptions", "/pharmacy/prescriptions"],
  ["Incoming e-prescriptions", "/pharmacy/incoming-prescriptions"],
  ["Scan a QR script", "/pharmacy/scan"],
  ["Connect software", "/pharmacy/connect"],
  ["Billing", "/pharmacy/billing"],
  ["Insurance claims", "/pharmacy/insurance-claims"],
  ["Settings", "/pharmacy/settings"],
  ["Staff", "/pharmacy/staff"]
] as const;

export const ADMIN_NAV = [
  ["Admin", "/admin"],
  ["Dispatch board", "/admin/dispatch"],
  ["Pharmacies", "/admin/pharmacies"],
  ["Pharmacy applications", "/admin/pharmacy-applications"],
  ["Billing", "/admin/billing"],
  ["Insurance", "/admin/insurance"],
  ["Medicines", "/admin/medicines"],
  ["Users", "/admin/users"],
  ["Imports", "/admin/imports"],
  ["Audit Logs", "/admin/audit-logs"]
] as const;

export const DOCTOR_NAV = [
  ["Prescriptions", "/doctor/prescriptions"],
  ["Write a prescription", "/doctor/prescriptions/new"],
  ["Renewal requests", "/doctor/renewal-requests"],
  ["Formulary lookup", "/doctor/formulary"],
  ["Patients", "/doctor/patients"],
  ["Profile", "/doctor/profile"]
] as const;

export const SHOP_NAV = [
  ["Find medicine", "/shop"],
  ["My orders", "/shop/orders"],
  ["My prescriptions", "/shop/prescriptions"],
  ["Repeat refills", "/shop/refills"],
  ["Addresses", "/shop/addresses"],
  ["Insurance", "/shop/insurance"]
] as const;

/** Where each role lands after signing in. */
export const ROLE_HOME: Record<string, string> = {
  PLATFORM_ADMIN: "/admin",
  PHARMACY_OWNER: "/pharmacy/dashboard",
  PHARMACY_STAFF: "/pharmacy/dashboard",
  DOCTOR: "/doctor/prescriptions",
  CUSTOMER: "/home",
  DRIVER: "/driver"
};

export const ORDER_STATUS_LABELS: Record<string, string> = {
  PENDING: "Awaiting pharmacy",
  SCHEDULED: "Scheduled",
  CONFIRMED: "Confirmed",
  READY: "Ready for pickup",
  ASSIGNED: "Driver assigned",
  IN_TRANSIT: "On the way",
  DELIVERED: "Delivered",
  COLLECTED: "Collected",
  PARTIALLY_CANCELLED: "Partly cancelled",
  CANCELLED: "Cancelled"
};
