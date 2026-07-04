export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export const PHARMACY_NAV = [
  ["Dashboard", "/pharmacy/dashboard"],
  ["Inventory", "/pharmacy/inventory"],
  ["Imports", "/pharmacy/imports"],
  ["Sales", "/pharmacy/sales"],
  ["Prescriptions", "/pharmacy/prescriptions"],
  ["Settings", "/pharmacy/settings"],
  ["Staff", "/pharmacy/staff"]
] as const;

export const ADMIN_NAV = [
  ["Admin", "/admin"],
  ["Pharmacies", "/admin/pharmacies"],
  ["Medicines", "/admin/medicines"],
  ["Users", "/admin/users"],
  ["Imports", "/admin/imports"],
  ["Audit Logs", "/admin/audit-logs"]
] as const;

