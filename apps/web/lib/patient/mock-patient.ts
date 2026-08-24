/**
 * Demo records for the signed-in patient area.
 *
 * The same role `lib/catalog/mock-catalog.ts` plays for the catalogue: the
 * prescription, order, refill and account modules have no patient-facing API
 * yet, so these stand in. Everything is fictional and chosen to exercise every
 * state the UI has to render rather than to look tidy: a partially dispensed
 * prescription, an expired one, an order mid-delivery, a paused refill, and a
 * refill whose prescription runs out before the next delivery.
 *
 * Pharmacy names match the ones already used across the public pages, so the
 * demo tells one consistent story. No real person or business is described.
 */

import type {
  Address,
  NotificationPreferences,
  Order,
  PatientProfile,
  PaymentMethod,
  Prescription,
  Refill
} from "./types";

// Everything below is dated relative to late August 2026, which is what the
// demo treats as "today".

export const MOCK_PROFILE: PatientProfile = {
  firstName: "Marc",
  lastName: "Zeinoun",
  email: "marc.zeinoun@example.com",
  phone: "+961 3 418 902"
};

export const MOCK_ADDRESSES: Address[] = [
  {
    id: "addr-home",
    label: "Home",
    line1: "123 Rue Sursock",
    building: "Bloc B, 4th floor",
    area: "Achrafieh",
    city: "Beirut",
    notes: "Intercom is on the left of the gate.",
    isDefault: true
  },
  {
    id: "addr-work",
    label: "Work",
    line1: "8 Rue Makdessi",
    building: "Kassab Building, 2nd floor",
    area: "Hamra",
    city: "Beirut",
    notes: "Reception holds deliveries until 6 PM.",
    isDefault: false
  }
];

export const MOCK_PAYMENTS: PaymentMethod[] = [
  { id: "pay-visa", kind: "card", brand: "Visa", last4: "4242", expiry: "08/29", isDefault: true },
  { id: "pay-cash", kind: "cash", isDefault: false }
];

export const MOCK_NOTIFICATIONS: NotificationPreferences = {
  orderUpdates: true,
  deliveryUpdates: true,
  prescriptionReminders: true,
  refillReminders: true,
  productNews: false
};

export const MOCK_PRESCRIPTIONS: Prescription[] = [
  {
    id: "HC-RX-38292",
    status: "active",
    prescriber: { name: "Dr. Sarah Haddad", specialty: "General Medicine" },
    issuedOn: "2026-08-18",
    validUntil: "2026-09-18",
    accessPin: "704 218",
    items: [
      {
        medicineId: "augmentin-1g",
        name: "Augmentin 1g",
        generic: "Amoxicillin / Clavulanic Acid",
        prescribed: 14,
        dispensed: 0,
        unit: "tablets",
        dosage: "1 tablet twice daily"
      },
      {
        medicineId: "brufen-400",
        name: "Brufen 400mg",
        generic: "Ibuprofen",
        prescribed: 30,
        dispensed: 0,
        unit: "tablets",
        dosage: "1 tablet after meals, as needed"
      },
      {
        medicineId: "ventolin-inhaler",
        name: "Ventolin 100mcg",
        generic: "Salbutamol",
        prescribed: 1,
        dispensed: 0,
        unit: "inhaler",
        dosage: "2 puffs when short of breath"
      }
    ]
  },
  {
    id: "HC-RX-48814",
    status: "partial",
    prescriber: { name: "Dr. Rami Khoury", specialty: "Cardiology" },
    issuedOn: "2026-07-30",
    validUntil: "2026-10-30",
    accessPin: "551 037",
    items: [
      {
        medicineId: "lipitor-20",
        name: "Lipitor 20mg",
        generic: "Atorvastatin",
        prescribed: 90,
        dispensed: 30,
        unit: "tablets",
        dosage: "1 tablet each evening"
      },
      {
        medicineId: "concor-5",
        name: "Concor 5mg",
        generic: "Bisoprolol",
        prescribed: 60,
        dispensed: 30,
        unit: "tablets",
        dosage: "1 tablet each morning"
      }
    ]
  },
  {
    id: "HC-RX-31160",
    status: "completed",
    prescriber: { name: "Dr. Sarah Haddad", specialty: "General Medicine" },
    issuedOn: "2026-05-12",
    validUntil: "2026-06-12",
    accessPin: "228 940",
    items: [
      {
        medicineId: "zithromax-500",
        name: "Zithromax 500mg",
        generic: "Azithromycin",
        prescribed: 3,
        dispensed: 3,
        unit: "tablets",
        dosage: "1 tablet daily for 3 days"
      }
    ]
  },
  {
    id: "HC-RX-29017",
    status: "expired",
    prescriber: { name: "Dr. Nadia Aoun", specialty: "Dermatology" },
    issuedOn: "2026-02-04",
    validUntil: "2026-05-04",
    accessPin: "163 775",
    items: [
      {
        medicineId: "voltaren-emulgel",
        name: "Voltaren Emulgel",
        generic: "Diclofenac",
        prescribed: 2,
        dispensed: 1,
        unit: "tubes",
        dosage: "Apply to the affected area twice daily"
      }
    ]
  }
];

export const MOCK_ORDERS: Order[] = [
  {
    id: "HC-24082",
    placedAt: "2026-08-24",
    stage: "transit",
    arrivalWindow: "4:30 - 5:00 PM",
    scheduled: false,
    deliveredAt: null,
    address: MOCK_ADDRESSES[0],
    paymentLabel: "Visa ending 4242",
    medicationTotal: 31.5,
    deliveryFee: 3,
    reachedAt: {
      confirmed: "3:42 PM",
      preparing: "3:48 PM",
      collecting: "4:05 PM"
    },
    rating: null,
    reviewComment: "",
    lines: [
      {
        medicineId: "augmentin-1g",
        name: "Augmentin 1g",
        generic: "Amoxicillin / Clavulanic Acid",
        quantity: 1,
        unitPrice: 12.5,
        pharmacy: "Cedar Care Pharmacy",
        prescriptionId: "HC-RX-38292"
      },
      {
        medicineId: "panadol-extra",
        name: "Panadol Extra 500mg / 65mg",
        generic: "Paracetamol / Caffeine",
        quantity: 2,
        unitPrice: 3.4,
        pharmacy: "Cedar Care Pharmacy",
        prescriptionId: null
      },
      {
        medicineId: "lipitor-20",
        name: "Lipitor 20mg",
        generic: "Atorvastatin",
        quantity: 1,
        unitPrice: 12.2,
        pharmacy: "Verdun Health Pharmacy",
        prescriptionId: "HC-RX-48814"
      }
    ]
  },
  {
    id: "HC-24019",
    placedAt: "2026-08-22",
    stage: "preparing",
    arrivalWindow: "Tomorrow, 9:00 - 11:00 AM",
    scheduled: true,
    deliveredAt: null,
    address: MOCK_ADDRESSES[1],
    paymentLabel: "Cash on delivery",
    medicationTotal: 9.6,
    deliveryFee: 3,
    reachedAt: { confirmed: "11:12 AM", preparing: "11:20 AM" },
    rating: null,
    reviewComment: "",
    lines: [
      {
        medicineId: "zyrtec-10",
        name: "Zyrtec 10mg",
        generic: "Cetirizine",
        quantity: 1,
        unitPrice: 5.6,
        pharmacy: "Achrafieh Pharmacy",
        prescriptionId: null
      },
      {
        medicineId: "panadol-500",
        name: "Panadol 500mg",
        generic: "Paracetamol",
        quantity: 1,
        unitPrice: 4,
        pharmacy: "Achrafieh Pharmacy",
        prescriptionId: null
      }
    ]
  },
  {
    id: "HC-23872",
    placedAt: "2026-08-18",
    stage: "delivered",
    arrivalWindow: "4:00 - 5:00 PM",
    scheduled: false,
    deliveredAt: "5:02 PM",
    address: MOCK_ADDRESSES[0],
    paymentLabel: "Visa ending 4242",
    medicationTotal: 21.5,
    deliveryFee: 3,
    reachedAt: {
      confirmed: "3:31 PM",
      preparing: "3:40 PM",
      collecting: "4:12 PM",
      transit: "4:26 PM",
      delivered: "5:02 PM"
    },
    rating: null,
    reviewComment: "",
    lines: [
      {
        medicineId: "lipitor-20",
        name: "Lipitor 20mg",
        generic: "Atorvastatin",
        quantity: 1,
        unitPrice: 12.2,
        pharmacy: "Verdun Health Pharmacy",
        prescriptionId: "HC-RX-48814"
      },
      {
        medicineId: "concor-5",
        name: "Concor 5mg",
        generic: "Bisoprolol",
        quantity: 1,
        unitPrice: 9.3,
        pharmacy: "Verdun Health Pharmacy",
        prescriptionId: "HC-RX-48814"
      }
    ]
  },
  {
    id: "HC-23140",
    placedAt: "2026-06-02",
    stage: "delivered",
    arrivalWindow: "6:00 - 7:00 PM",
    scheduled: false,
    deliveredAt: "6:38 PM",
    address: MOCK_ADDRESSES[0],
    paymentLabel: "Cash on delivery",
    medicationTotal: 7.8,
    deliveryFee: 3,
    reachedAt: {
      confirmed: "5:14 PM",
      preparing: "5:22 PM",
      collecting: "5:58 PM",
      transit: "6:09 PM",
      delivered: "6:38 PM"
    },
    rating: 5,
    reviewComment: "Arrived earlier than the window.",
    lines: [
      {
        medicineId: "zithromax-500",
        name: "Zithromax 500mg",
        generic: "Azithromycin",
        quantity: 1,
        unitPrice: 7.8,
        pharmacy: "Mar Elias Pharmacy",
        prescriptionId: "HC-RX-31160"
      }
    ]
  }
];

export const MOCK_REFILLS: Refill[] = [
  {
    id: "rf-lipitor",
    medicineId: "lipitor-20",
    name: "Lipitor 20mg",
    generic: "Atorvastatin",
    everyDays: 30,
    nextRefill: "2026-09-04",
    status: "active",
    preference: "morning",
    addressId: "addr-home",
    prescriptionId: "HC-RX-48814"
  },
  {
    id: "rf-concor",
    medicineId: "concor-5",
    name: "Concor 5mg",
    generic: "Bisoprolol",
    everyDays: 60,
    nextRefill: "2026-11-19",
    status: "active",
    preference: "morning",
    addressId: "addr-home",
    /**
     * Deliberately falls after HC-RX-48814 expires on 30 Oct, so the refill
     * screen has to show the "prescription runs out before this delivery"
     * warning instead of quietly implying another refill is guaranteed.
     */
    prescriptionId: "HC-RX-48814"
  },
  {
    id: "rf-zyrtec",
    medicineId: "zyrtec-10",
    name: "Zyrtec 10mg",
    generic: "Cetirizine",
    everyDays: 45,
    nextRefill: "2026-09-15",
    status: "paused",
    preference: "evening",
    addressId: "addr-work",
    prescriptionId: null
  }
];
