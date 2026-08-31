export type UserRole = "PLATFORM_ADMIN" | "PHARMACY_OWNER" | "PHARMACY_STAFF" | "DOCTOR" | "CUSTOMER" | "DRIVER";

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
  is_on_call: boolean;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  role: UserRole;
  pharmacy?: string;
  pharmacy_detail?: Pharmacy;
  is_active: boolean;
}

export type ProductCategory = "MEDICINE" | "SUPPLEMENT" | "PARAPHARMACY";
export type PriceRegime = "REGULATED" | "FREE";

export interface Medicine {
  id: string;
  brand_name: string;
  generic_name: string;
  strength: string;
  form: string;
  route?: string;
  manufacturer?: string;
  /** Active-ingredient composition, e.g. "Atorvastatin (calcium) - 10mg". The real
   *  "active ingredient" text — `generic_name` is populated on a small fraction of
   *  MoPH-synced products. */
  ingredients?: string;
  /** ATC classification code. Discovery/validation metadata only — never a basis for
   *  treating two products as interchangeable. */
  classification?: string;
  registration_number?: string;
  market_status?: "MARKETED" | "NON_MARKETED";
  image?: string | null;
  is_active: boolean;
  display_name: string;
  category?: ProductCategory;
  price_regime?: PriceRegime;
  regulated_price?: string | null;
  regulated_price_reference?: string;
  requires_prescription?: boolean;
  is_price_regulated?: boolean;
  /** True when the medicine is on an NSSF (National Social Security Fund) reimbursable
   *  list. Unrelated to MoPH import subsidy. */
  nssf_covered?: boolean;
  /** NSSF reference (reimbursement-ceiling) price, decimal string. Null when covered but
   *  the figure is not yet on file, or when not covered. */
  nssf_reference_price?: string | null;
  /** Percentage of the reference price the NSSF reimburses, decimal string, e.g. "80.00". */
  nssf_reimbursement_rate?: string | null;
  /** Which NSSF list/decision the coverage was taken from. */
  nssf_source_reference?: string;
  nssf_updated_at?: string | null;
  /** Percentage the patient still pays out of pocket (100 - rate); null when the rate is
   *  unknown. Server-derived, read-only. */
  nssf_patient_share_percentage?: string | null;
  /** Pack presentation from the MoPH source, e.g. "30" or "100ml" — count or volume
   *  depending on the product; count-only values need a unit from `form` to read as a
   *  pack size. */
  presentation?: string;
  country?: string;
  /** Lebanese importer/distributor, distinct from `manufacturer`. */
  agent?: string;
  /** MoPH's own brand/generic classification (G / B / BioTech / BioHuman) — more
   *  reliable than inferring brand-vs-generic from name/ingredient matching. */
  brand_generic?: string;
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
  medicine: Pick<
    Medicine,
    | "id"
    | "brand_name"
    | "generic_name"
    | "strength"
    | "form"
    | "route"
    | "image"
    | "manufacturer"
    | "ingredients"
    | "classification"
    | "registration_number"
    | "presentation"
    | "country"
    | "agent"
    | "brand_generic"
    | "market_status"
    | "nssf_covered"
    | "nssf_reference_price"
    | "nssf_reimbursement_rate"
  > & {
    category?: ProductCategory;
    requires_prescription?: boolean;
  };
  pharmacy: Pick<Pharmacy, "id" | "name" | "address" | "city" | "area" | "phone" | "whatsapp" | "email" | "is_on_call"> & {
    rating: number;
    rating_count: number;
    fulfillment_success_rate: number;
    accepts_online_orders: boolean;
    delivery_enabled: boolean;
    preparation_minutes: number;
  };
  availability_status: "Available" | "Low stock" | "Unavailable" | "Unknown";
  available_up_to: number;
  quantity_cap: number;
  unit_price: string | null;
  is_price_regulated: boolean;
  price_note: string;
  distance_km: number | null;
  soonest_expiry?: string | null;
  rank_score: number;
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

export type PrescriptionUploadStatus = "PENDING_REVIEW" | "ACCEPTED" | "REJECTED";

export interface OcrMedication {
  name: string;
  strength: string;
  quantity: number | null;
  /** Dosing notation verbatim from the page ("1-0-1"); `directions` holds the plain
   * reading of it. Only the vision OCR providers fill this in. */
  dose_pattern: string;
  directions: string;
  duration: string;
  refills: number | null;
  /** Server-side reconciliation of `name` against the medicine catalog: the matched
   * Medicine id ("" if nothing matched), that row's display name, and a 0-1 score. */
  medicine_id: string;
  catalog_name: string;
  match_confidence: number;
}

/** The structured read of an uploaded scan: what OCR + extraction pulled off the
 * page. Shown to the patient read-only; editable by a pharmacist on review. */
export interface OcrFields {
  patient_name: string;
  patient_phone: string;
  doctor_name: string;
  prescription_date: string;
  medications: OcrMedication[];
  notes: string;
}

export interface PrescriptionUpload {
  id: string;
  status: PrescriptionUploadStatus;
  doctor_name: string;
  prescription_date?: string;
  notes: string;
  rejection_reason: string;
  ocr_fields?: OcrFields;
  /** 0-1 reliability of the structured read; null when no extraction ran. */
  ocr_confidence?: number | null;
  /** A read exists but is too weak to show as a medication list - show a fallback notice. */
  ocr_low_confidence?: boolean;
  ocr_review_requested?: boolean;
  ocr_review_note?: string;
  file_name?: string;
  file_mime_type?: string;
  file_size?: number;
  is_expired: boolean;
  quality_warnings: string[];
  download_url?: string;
  created_at: string;
  updated_at: string;
}

export interface PrescriptionOcrCandidate {
  raw_line: string;
  name_guess: string;
  medicine_id: string | null;
  medicine_name: string;
  confidence: number;
  quantity_guess: number | null;
  dosage_guess: string;
}

export interface PrescriptionOcrResult {
  provider: string;
  ocr_text: string;
  candidates: PrescriptionOcrCandidate[];
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

/* --- Pharmacy clients (CRM) ------------------------------------------------------- */

export interface Client {
  id: string;
  full_name: string;
  phone: string;
  email?: string;
  date_of_birth?: string | null;
  address?: string;
  area?: string;
  allergies?: string;
  chronic_conditions?: string;
  notes?: string;
  insurance_provider?: string;
  insurance_number?: string;
  credit_limit: string;
  marketing_opt_in: boolean;
  is_active: boolean;
  balance_due: string;
  created_at: string;
}

export interface ClientHistory {
  visits: number;
  total_spent: string;
  average_basket: string;
  balance_due: string;
  last_visit: string | null;
  days_since_last_visit: number | null;
  top_products: { medicine_id: string; name: string; units: number; spend: string }[];
  recent_sales: { id: string; invoice_number: string; total: string; sale_datetime: string }[];
}

export interface ClientLedgerEntry {
  id: string;
  entry_type: "CHARGE" | "PAYMENT" | "ADJUSTMENT";
  amount: string;
  memo?: string;
  created_by_email?: string;
  created_at: string;
}

/* --- E-prescriptions -------------------------------------------------------------- */

export type PrescriptionStatus = "ISSUED" | "PARTIALLY_DISPENSED" | "FULLY_DISPENSED" | "EXPIRED" | "CANCELLED";

export interface Doctor {
  id: string;
  license_number: string;
  full_name: string;
  specialty: string;
  email: string;
  phone: string;
  clinic_name: string;
  clinic_address: string;
  clinic_area: string;
  is_activated: boolean;
  activated_at?: string | null;
  is_active: boolean;
}

export interface PrescriptionItem {
  id: string;
  medicine?: string | null;
  medicine_detail?: Medicine;
  medicine_text: string;
  quantity_prescribed: number;
  quantity_dispensed: number;
  quantity_remaining: number;
  unit: string;
  dosage_instructions: string;
  allow_generic_substitution: boolean;
}

export interface Prescription {
  id: string;
  code: string;
  doctor_name: string;
  doctor_license: string;
  target_pharmacy?: string | null;
  target_pharmacy_name?: string | null;
  renewed_from?: string | null;
  renewed_from_code?: string | null;
  patient_name: string;
  patient_email?: string;
  patient_phone?: string;
  patient_fax?: string;
  patient_date_of_birth?: string | null;
  diagnosis_note?: string;
  status: PrescriptionStatus;
  issued_at: string;
  valid_until: string;
  cancelled_at?: string | null;
  cancellation_reason?: string;
  email_sent_at?: string | null;
  fax_sent_at?: string | null;
  is_expired: boolean;
  is_consumable: boolean;
  items: PrescriptionItem[];
  dispenses: {
    id: string;
    pharmacy_name: string;
    pharmacist_name: string;
    dispensed_at: string;
    items: { prescription_item: string; name: string; quantity: number }[];
  }[];
  one_time_secrets?: { pin: string; qr_url: string; qr_svg: string };
}

export type RenewalRequestStatus = "PENDING" | "APPROVED" | "DENIED";

export interface PrescriptionRenewalRequest {
  id: string;
  prescription: string;
  prescription_code: string;
  patient_name: string;
  requested_by_pharmacy: string;
  pharmacy_name: string;
  note: string;
  status: RenewalRequestStatus;
  response_note: string;
  responded_at?: string | null;
  new_prescription?: string | null;
  new_prescription_code?: string | null;
  created_at: string;
}

export interface PublicPrescription {
  id: string;
  code: string;
  status: PrescriptionStatus;
  issued_at: string;
  valid_until: string;
  is_expired: boolean;
  is_consumable: boolean;
  patient_name: string;
  patient_date_of_birth?: string | null;
  doctor: { full_name: string; license_number: string; specialty: string; clinic_name: string };
  diagnosis_note: string;
  items: {
    id: string;
    medicine_text: string;
    medicine_id?: string | null;
    quantity_prescribed: number;
    quantity_dispensed: number;
    quantity_remaining: number;
    unit: string;
    dosage_instructions: string;
    allow_generic_substitution: boolean;
  }[];
  dispense_history: { pharmacy_name: string; dispensed_at: string; units: number }[];
  dispense_ticket: string;
  ticket_expires_in_seconds: number;
  pharmacy?: { id: string; name: string };
}

/* --- Shopper orders --------------------------------------------------------------- */

export interface DeliveryAddress {
  id: string;
  label: string;
  contact_name: string;
  phone: string;
  address: string;
  area: string;
  city: string;
  building_notes?: string;
  latitude: string;
  longitude: string;
  is_default: boolean;
}

export interface QuoteLine {
  medicine: string;
  medicine_name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  is_price_regulated: boolean;
}

export interface QuoteAllocation {
  pharmacy: string;
  pharmacy_name: string;
  pharmacy_area: string;
  distance_km: number;
  rating: number;
  fulfillment_success_rate: number;
  preparation_minutes: number;
  subtotal: string;
  lines: QuoteLine[];
}

export interface BasketQuote {
  allocations: QuoteAllocation[];
  unfulfilled: { medicine: string; medicine_name: string; quantity_short: number }[];
  items_subtotal: string;
  pharmacy_count: number;
  explanation: string[];
}

export type OrderStatus =
  | "PENDING"
  | "SCHEDULED"
  | "CONFIRMED"
  | "READY"
  | "ASSIGNED"
  | "IN_TRANSIT"
  | "DELIVERED"
  | "COLLECTED"
  | "PARTIALLY_CANCELLED"
  | "CANCELLED";

export interface OrderLine {
  id: string;
  medicine: string;
  medicine_detail: Medicine;
  quantity: number;
  unit_price: string;
  line_total: string;
  is_price_regulated: boolean;
}

export interface OrderFulfillment {
  id: string;
  pharmacy: string;
  pharmacy_name: string;
  pharmacy_area: string;
  pharmacy_phone: string;
  status: "PENDING" | "ACCEPTED" | "READY" | "PICKED_UP" | "DELIVERED" | "COLLECTED" | "REJECTED" | "CANCELLED";
  subtotal: string;
  accepted_at?: string | null;
  ready_at?: string | null;
  picked_up_at?: string | null;
  completed_at?: string | null;
  rejection_reason?: string;
  lines: OrderLine[];
  handover_code?: string;
  order?: string;
  order_reference?: string;
  order_status?: OrderStatus;
  order_area?: string;
  contact_name?: string;
  scheduled_for?: string | null;
  fulfillment_type?: "DELIVERY" | "PICKUP";
  is_shared_order?: boolean;
}

export type PaymentProvider = "COD" | "MOCK_GATEWAY";
export type PaymentStatus = "PENDING" | "PAID" | "FAILED" | "REFUNDED";

export interface Payment {
  id: string;
  order: string;
  provider: PaymentProvider;
  status: PaymentStatus;
  amount: string;
  currency: string;
  external_reference: string;
  paid_at: string | null;
  failure_reason: string;
  created_at: string;
}

export interface PaymentMethod {
  code: PaymentProvider;
  label: string;
}

export interface Order {
  id: string;
  reference: string;
  status: OrderStatus;
  fulfillment_type: "DELIVERY" | "PICKUP";
  source: "WEB" | "RECURRING";
  /** The e-prescription this order was dispensed against, when it needed one. */
  prescription?: string | null;
  contact_name: string;
  contact_phone: string;
  address: string;
  area: string;
  city: string;
  delivery_notes?: string;
  scheduled_for?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  items_subtotal: string;
  delivery_fee: string;
  total: string;
  notes?: string;
  cancelled_reason?: string;
  fulfillments: OrderFulfillment[];
  payment: Payment | null;
  /** The shopper's own review of this order, once they have left one. */
  review: { rating: number; comment: string; pharmacy: string } | null;
  created_at: string;
}

export interface RecurringOrder {
  id: string;
  label: string;
  address: string;
  items: { medicine: string; quantity: number }[];
  /** `items` resolved against the catalogue, so a schedule can be named without extra lookups. */
  item_details?: {
    medicine: string;
    name: string;
    generic_name: string;
    quantity: number;
    requires_prescription: boolean;
  }[];
  prescription?: string | null;
  prescription_code_value?: string;
  interval_days: number;
  preferred_hour: number;
  next_run_at: string;
  last_run_at?: string | null;
  occurrences_created: number;
  is_active: boolean;
  last_error?: string;
}

/* --- Messaging (WhatsApp chat) ------------------------------------------------------ */

export type MessageDirection = "OUTBOUND" | "INBOUND";
export type MessageStatus = "QUEUED" | "SENT" | "DELIVERED" | "FAILED" | "RECEIVED";

export interface ChatMessage {
  id: string;
  direction: MessageDirection;
  body: string;
  status: MessageStatus;
  sender_email: string | null;
  failure_reason: string;
  created_at: string;
}

/* --- Delivery / dispatch ---------------------------------------------------------- */

export interface RouteStopTask {
  id: string;
  order_fulfillment: string;
  order_reference: string;
  contact_name: string;
  contact_phone: string;
  pharmacy_name: string;
  handover_code: string;
  fulfillment_status: string;
  units: number;
  is_done: boolean;
}

export interface RouteStop {
  id: string;
  sequence: number;
  kind: "PICKUP" | "DROPOFF";
  label: string;
  address: string;
  latitude: string;
  longitude: string;
  units: number;
  planned_arrival?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  arrived_at?: string | null;
  completed_at?: string | null;
  status: "PENDING" | "ARRIVED" | "DONE" | "FAILED" | "SKIPPED";
  failure_reason?: string;
  orders_served: number;
  tasks: RouteStopTask[];
}

export interface DeliveryRoute {
  id: string;
  driver?: string | null;
  driver_name: string;
  status: "PROPOSED" | "OFFERED" | "ACTIVE" | "COMPLETED" | "CANCELLED";
  planned_distance_km: string;
  planned_duration_minutes: number;
  naive_distance_km: string;
  distance_saved_km: number;
  plan_version: number;
  planner_notes: string;
  orders_count: number;
  created_at: string;
  stops: RouteStop[];
}

export interface DispatchSummary {
  jobs: number;
  assigned_jobs: number;
  unassigned_jobs: number;
  routes_used: number;
  drivers_available: number;
  stops: number;
  pickup_stops: number;
  shared_pickup_stops: number;
  pickup_visits_avoided: number;
  baseline_scope: string;
  naive_distance_km: number;
  optimised_distance_km: number;
  distance_saved_km: number;
  distance_saved_percent: number;
}

export interface Driver {
  id: string;
  full_name: string;
  phone: string;
  vehicle_type: "SCOOTER" | "CAR" | "BICYCLE";
  capacity_units: number;
  is_active: boolean;
  is_online: boolean;
  last_ping_at?: string | null;
}

/* --- Analytics -------------------------------------------------------------------- */

export interface StockSnapshot {
  sku_count: number;
  batch_count: number;
  units_on_hand: number;
  units_reserved: number;
  stock_value_at_cost: string;
  stock_value_at_retail: string;
  potential_margin_value: string;
  low_stock_skus: number;
  out_of_stock_batches: number;
  expired_batches: number;
  expired_value_at_cost: string;
  value_expiring_30d: string;
  units_expiring_30d: number;
  value_expiring_60d: string;
  units_expiring_60d: number;
  value_expiring_90d: string;
  units_expiring_90d: number;
}

export interface SalesSnapshot {
  window_days: number;
  revenue: string;
  cogs: string;
  gross_margin: string;
  gross_margin_percent: number;
  transactions: number;
  units_sold: number;
  average_basket: string;
  average_units_per_basket: number;
  transactions_per_day: number;
  discount_given: string;
  regulated_revenue: string;
  free_priced_revenue: string;
  regulated_share_percent: number;
  revenue_by_channel: Record<string, string>;
}

export interface TurnoverMetrics {
  window_days: number;
  cogs: string;
  average_inventory_at_cost: string;
  inventory_turnover: number;
  inventory_turnover_annualised: number;
  days_inventory_outstanding: number | null;
  gmroi: number;
  sell_through_percent: number;
}

export interface MovementClassification {
  window_days: number;
  counts: { A: number; B: number; C: number };
  top_movers: {
    medicine_id: string;
    name: string;
    units: number;
    revenue: string;
    revenue_share_percent: number;
    cumulative_share_percent: number;
    abc_class: "A" | "B" | "C";
    daily_velocity: number;
  }[];
  slow_movers: MovementClassification["top_movers"];
  dead_stock: { medicine_id: string; name: string; units: number; value_at_cost: string }[];
  dead_stock_days: number;
  skus_with_no_sales: number;
}

export interface ReplenishmentPlan {
  window_days: number;
  lead_time_days: number;
  service_level_percent: number;
  reorder_now_count: number;
  suggestions: {
    medicine_id: string;
    name: string;
    units_on_hand: number;
    avg_daily_demand: number;
    demand_std_dev: number;
    safety_stock: number;
    reorder_point: number;
    days_of_cover: number | null;
    suggested_order_quantity: number;
    needs_reorder: boolean;
  }[];
}

export interface AnalyticsOverview {
  pharmacy: { id: string; name: string; area: string };
  generated_at: string;
  stock: StockSnapshot;
  sales_30d: SalesSnapshot;
  sales_7d: SalesSnapshot;
  turnover: TurnoverMetrics;
  platform: {
    window_days: number;
    orders_received: number;
    orders_accepted: number;
    orders_rejected: number;
    acceptance_rate_percent: number;
    median_acceptance_minutes: number | null;
    rating_average: number;
    rating_count: number;
    fulfillment_success_rate: number;
  };
  revenue_series: { date: string; revenue: string; transactions: number }[];
}

export interface DemandSignals {
  window_days: number;
  area: string;
  signals: { medicine_id: string; name: string; requests: number; units_requested: number; source: string; you_stock_it: boolean }[];
}

export type InsightSeverity = "critical" | "warning" | "opportunity" | "info";

export interface Insight {
  id: string;
  severity: InsightSeverity;
  category: string;
  title: string;
  detail: string;
  metric: number;
}

export interface AnalyticsInsights {
  insights: Insight[];
}

export interface AnalyticsDigest {
  headline: string;
  paragraphs: string[];
  // Insight ids (see Insight.id) the digest was written from - every number an AI-narrated
  // digest mentions traces back to one of these, same idea as `tools_used` on an assistant
  // message.
  grounded_on: string[];
  provider: string;
  // True when no AI provider is configured, or the provider call failed - the digest then
  // falls back to the same rule-based Smart Insights cards AnalyticsInsights renders.
  stale: boolean;
  generated_at: string;
  fallback_reason?: string;
}

/* --- Integrations ----------------------------------------------------------------- */

export interface IntegrationKey {
  id: string;
  name: string;
  key_id: string;
  secret_fingerprint: string;
  scopes: string[];
  is_active: boolean;
  last_used_at?: string | null;
  request_count: number;
  created_at: string;
  secret?: string;
  setup_hint?: string;
}

export interface SkuMapping {
  id: string;
  external_code: string;
  external_name: string;
  medicine?: string | null;
  medicine_detail?: Medicine;
  match_method: "MANUAL" | "AUTO_EXACT" | "AUTO_FUZZY" | "UNMATCHED";
  match_confidence?: string | null;
  is_ignored: boolean;
  last_seen_at?: string | null;
}

export interface SyncRun {
  id: string;
  kind: "STOCK" | "SALES";
  status: "APPLIED" | "PARTIAL" | "REJECTED" | "REPLAYED";
  idempotency_key: string;
  rows_received: number;
  rows_applied: number;
  rows_unmapped: number;
  rows_failed: number;
  created_at: string;
}

export interface OnboardingStatus {
  pharmacy: string;
  steps: { key: string; title: string; done: boolean; detail?: string; hint?: string }[];
  completed_steps: number;
  total_steps: number;
  last_sync: SyncRun | null;
}

export interface WebhookEndpoint {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  last_delivery_at?: string | null;
  consecutive_failures: number;
  created_at: string;
}

/* --- Billing ------------------------------------------------------------------------ */

export interface SubscriptionPlan {
  id: string;
  name: string;
  monthly_fee: string;
  service_fee_per_request: string;
  is_active: boolean;
  created_at: string;
}

export interface PharmacySubscription {
  id: string;
  pharmacy: string;
  pharmacy_name: string;
  plan: string;
  plan_detail: SubscriptionPlan;
  status: "ACTIVE" | "PAST_DUE" | "CANCELLED";
  current_period_start: string;
  current_period_end?: string | null;
}

export interface PlatformServiceFee {
  id: string;
  pharmacy: string;
  pharmacy_name: string;
  fulfillment: string;
  order_reference: string;
  amount: string;
  status: "PENDING" | "INVOICED" | "PAID" | "WAIVED";
  created_at: string;
}

export interface PlatformRevenueOverview {
  active_subscriptions: number;
  monthly_recurring_revenue: string;
  service_fees_collected: string;
  service_fees_pending: string;
  service_fee_requests: number;
}

/* --- Insurance / copayment --------------------------------------------------------- */

export interface InsuranceProvider {
  id: string;
  name: string;
  phone?: string;
  notes?: string;
  is_active: boolean;
  created_at: string;
}

export interface InsurancePlan {
  id: string;
  provider: string;
  provider_name: string;
  name: string;
  coverage_percentage: string;
  copay_minimum: string;
  is_active: boolean;
  created_at: string;
}

export interface PublicInsurancePlan {
  id: string;
  provider_name: string;
  name: string;
  coverage_percentage: string;
  copay_minimum: string;
}

export interface PatientInsurancePolicy {
  id: string;
  plan: string;
  plan_detail: InsurancePlan;
  customer_user?: string | null;
  client?: string | null;
  member_id: string;
  holder_name: string;
  valid_until?: string | null;
  is_active: boolean;
  created_at: string;
}

export type InsuranceClaimStatus = "SUBMITTED" | "APPROVED" | "REJECTED" | "PAID" | "CANCELLED";

export interface InsuranceClaim {
  id: string;
  order_fulfillment?: string | null;
  sale?: string | null;
  order_reference?: string;
  invoice_number?: string;
  policy: string;
  policy_detail: PatientInsurancePolicy;
  pharmacy: string;
  pharmacy_name: string;
  billed_amount: string;
  covered_amount: string;
  patient_copay: string;
  status: InsuranceClaimStatus;
  approval_code?: string;
  rejection_reason?: string;
  approved_at?: string | null;
  paid_at?: string | null;
  created_at: string;
}

export interface PharmacyApplication {
  id: string;
  pharmacy_name: string;
  owner_name: string;
  email: string;
  phone: string;
  city: string;
  area: string;
  license_number: string;
  message: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  review_note: string;
  reviewed_at: string | null;
  created_pharmacy: string | null;
  created_at: string;
}

/* --- Dispatch order offers --------------------------------------------------------- */

export interface OrderOffer {
  driver: string;
  driver_name: string;
  marginal_distance_km: number;
  total_distance_km: number;
  stops_after: number;
  shares_a_pickup: boolean;
}


/* --- In-app assistant -------------------------------------------------------------- */

export interface AssistantSession {
  persona: "guest" | "customer" | "doctor" | "pharmacy" | "admin" | "driver";
  label: string;
  greeting: string;
  suggestions: string[];
  signed_in: boolean;
}

export interface AssistantReply {
  conversation_id: string;
  reply: string;
  intent: string;
  persona: AssistantSession["persona"];
  source: string;
  suggestions: string[];
  tools_used: string[];
  /**
   * How the API described the position it ranked this answer from, or null if it had none.
   * Shown to the person so "nearest to you" is checkable rather than taken on trust.
   */
  location_used: string | null;
}

/**
 * One item from the in-app notification feed (`GET /api/notifications/`). The feed is
 * computed fresh on every poll, so `id` is stable and encodes the state it describes
 * (e.g. `order:<uuid>:READY`) - the client de-dupes popups on it. Display text is built
 * on the client from `kind` + `params` against the `notifications.kinds.*` messages.
 */
export interface NotificationItem {
  id: string;
  kind: string;
  href: string;
  occurred_at: string | null;
  params: Record<string, string | number>;
}

export interface ShopperLocation {
  latitude: string;
  longitude: string;
  accuracy_metres: number | null;
  source: "DEVICE" | "ADDRESS" | "MANUAL";
  /** Area name derived server-side from the coordinates - never sent by the client. */
  label: string;
  updated_at: string;
}
