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
  ["Scan a QR script", "/pharmacy/scan"],
  ["Connect software", "/pharmacy/connect"],
  ["Billing", "/pharmacy/billing"],
  ["Settings", "/pharmacy/settings"],
  ["Staff", "/pharmacy/staff"]
] as const;

export const ADMIN_NAV = [
  ["Admin", "/admin"],
  ["Dispatch board", "/admin/dispatch"],
  ["Pharmacies", "/admin/pharmacies"],
  ["Pharmacy applications", "/admin/pharmacy-applications"],
  ["Billing", "/admin/billing"],
  ["Medicines", "/admin/medicines"],
  ["Users", "/admin/users"],
  ["Imports", "/admin/imports"],
  ["Audit Logs", "/admin/audit-logs"]
] as const;

export const DOCTOR_NAV = [
  ["Prescriptions", "/doctor/prescriptions"],
  ["Write a prescription", "/doctor/prescriptions/new"],
  ["Patients", "/doctor/patients"],
  ["Profile", "/doctor/profile"]
] as const;

export const SHOP_NAV = [
  ["Find medicine", "/shop"],
  ["My orders", "/shop/orders"],
  ["Repeat refills", "/shop/refills"],
  ["Addresses", "/shop/addresses"]
] as const;

/** Where each role lands after signing in. */
export const ROLE_HOME: Record<string, string> = {
  PLATFORM_ADMIN: "/admin",
  PHARMACY_OWNER: "/pharmacy/dashboard",
  PHARMACY_STAFF: "/pharmacy/dashboard",
  DOCTOR: "/doctor/prescriptions",
  CUSTOMER: "/shop",
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
