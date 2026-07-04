export type UserRole = "PLATFORM_ADMIN" | "PHARMACY_OWNER" | "PHARMACY_STAFF" | "DOCTOR";

export interface Pharmacy {
  id: string;
  name: string;
  license_number?: string;
  address: string;
  city: string;
  area: string;
  phone: string;
  whatsapp?: string;
  email?: string;
  latitude?: string | null;
  longitude?: string | null;
  is_active: boolean;
  is_public: boolean;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  pharmacy?: string;
  pharmacy_detail?: Pharmacy;
  is_active: boolean;
}

export interface Medicine {
  id: string;
  brand_name: string;
  generic_name: string;
  strength: string;
  form: string;
  manufacturer?: string;
  is_active: boolean;
  display_name: string;
  aliases?: { id: string; alias: string; alias_type: string }[];
}

export interface InventoryBatch {
  id: string;
  medicine: string;
  medicine_detail: Medicine;
  batch_number: string;
  initial_quantity: number;
  current_quantity: number;
  expiry_date?: string;
  supplier_name?: string;
  purchase_cost?: string;
  selling_price: string;
  low_stock_threshold: number;
  public_availability_enabled: boolean;
  is_archived: boolean;
  is_low_stock: boolean;
  is_expired: boolean;
  is_expiring_soon: boolean;
  updated_at: string;
}

export interface PublicAvailability {
  medicine: Pick<Medicine, "id" | "brand_name" | "generic_name" | "strength" | "form">;
  pharmacy: Pick<Pharmacy, "id" | "name" | "address" | "city" | "area" | "phone" | "whatsapp" | "email">;
  availability_status: "Available" | "Low stock" | "Unavailable" | "Unknown";
  last_updated: string;
  disclaimer: string;
}

export interface Sale {
  id: string;
  invoice_number: string;
  sale_datetime: string;
  subtotal: string;
  discount_total: string;
  total: string;
  payment_method: string;
  status: string;
  staff_email: string;
  items: SaleItem[];
}

export interface SaleItem {
  id: string;
  medicine: string;
  medicine_detail: Medicine;
  batch_number: string;
  quantity: number;
  unit_price: string;
  discount: string;
  line_total: string;
}

export interface PrescriptionRecord {
  id: string;
  patient_name: string;
  doctor_name: string;
  prescription_date?: string;
  file_name?: string;
  file_mime_type?: string;
  file_size?: number;
  download_url?: string;
  created_at: string;
}

export interface InventoryImport {
  id: string;
  original_filename: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  created_count: number;
  skipped_count: number;
  error_summary?: string;
  created_at: string;
  rows?: InventoryImportRow[];
}

export interface InventoryImportRow {
  id: string;
  row_number: number;
  raw_medicine_name: string;
  matched_medicine_detail?: Medicine;
  match_confidence?: string;
  quantity?: number;
  selling_price?: string;
  status: string;
  error_message?: string;
}

export interface AuditLog {
  id: string;
  actor_email?: string;
  pharmacy_name?: string;
  action: string;
  entity_type: string;
  summary: string;
  created_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

