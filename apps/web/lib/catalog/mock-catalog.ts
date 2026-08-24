import type { MedicineSummary } from "./types";

/**
 * Demo catalogue for the patient surface.
 *
 * Used when the API is unreachable (design review, offline demos, screenshots)
 * so the slice always renders something believable instead of an error page.
 * Live data comes from `/public/search/` — see `lib/catalog/service.ts`.
 *
 * The entries are fictional stand-ins chosen to exercise every state the UI has
 * to handle: prescription and over-the-counter, brand and generic listings of
 * the same active ingredient, several strengths of one brand, and available /
 * limited / unavailable supply. Nothing here is clinical guidance.
 */
export const MOCK_CATALOG: MedicineSummary[] = [
  {
    id: "augmentin-1g",
    brand: "Augmentin",
    strength: "1g",
    generic: "Amoxicillin / Clavulanic Acid",
    form: "Tablet",
    packSize: "14 tablets",
    manufacturer: "Beecham",
    requiresPrescription: true,
    productType: "brand",
    availability: "available",
    fromPrice: 12.5,
    sourcingCount: 7,
    aliases: ["co-amoxiclav", "amoxiclav", "augmentine"]
  },
  {
    id: "augmentin-625",
    brand: "Augmentin",
    strength: "625mg",
    generic: "Amoxicillin / Clavulanic Acid",
    form: "Tablet",
    packSize: "16 tablets",
    manufacturer: "Beecham",
    requiresPrescription: true,
    productType: "brand",
    availability: "available",
    fromPrice: 8.9,
    sourcingCount: 6,
    aliases: ["co-amoxiclav", "amoxiclav"]
  },
  {
    id: "amoclav-1g",
    brand: "Amoclav",
    strength: "1g",
    generic: "Amoxicillin / Clavulanic Acid",
    form: "Tablet",
    packSize: "14 tablets",
    manufacturer: "Medipha",
    requiresPrescription: true,
    productType: "generic",
    availability: "limited",
    fromPrice: 6.2,
    sourcingCount: 3,
    aliases: ["amoxiclav"]
  },
  {
    id: "panadol-extra",
    brand: "Panadol Extra",
    strength: "500mg / 65mg",
    generic: "Paracetamol / Caffeine",
    form: "Tablet",
    packSize: "24 tablets",
    manufacturer: "Sterling Health",
    requiresPrescription: false,
    productType: "brand",
    availability: "available",
    fromPrice: 3.4,
    sourcingCount: 9,
    aliases: ["panadol", "acetaminophen", "paracetamol"]
  },
  {
    id: "panadol-500",
    brand: "Panadol",
    strength: "500mg",
    generic: "Paracetamol",
    form: "Tablet",
    packSize: "20 tablets",
    manufacturer: "Sterling Health",
    requiresPrescription: false,
    productType: "brand",
    availability: "available",
    fromPrice: 2.1,
    sourcingCount: 11,
    aliases: ["acetaminophen", "paracetamol"]
  },
  {
    id: "lipitor-20",
    brand: "Lipitor",
    strength: "20mg",
    generic: "Atorvastatin",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Parke-Davis",
    requiresPrescription: true,
    productType: "brand",
    availability: "limited",
    fromPrice: 18.75,
    sourcingCount: 4,
    aliases: ["statin"]
  },
  {
    id: "lipitor-40",
    brand: "Lipitor",
    strength: "40mg",
    generic: "Atorvastatin",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Parke-Davis",
    requiresPrescription: true,
    productType: "brand",
    availability: "unavailable",
    fromPrice: null,
    sourcingCount: 0,
    aliases: ["statin"]
  },
  {
    id: "atorvastatin-20",
    brand: "Atorvastatin Sandoz",
    strength: "20mg",
    generic: "Atorvastatin",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Sandoz",
    requiresPrescription: true,
    productType: "generic",
    availability: "available",
    fromPrice: 7.3,
    sourcingCount: 6,
    aliases: ["statin"]
  },
  {
    id: "ventolin-inhaler",
    brand: "Ventolin",
    strength: "100mcg",
    generic: "Salbutamol",
    form: "Inhaler",
    packSize: "200 doses",
    manufacturer: "Allen & Hanburys",
    requiresPrescription: true,
    productType: "brand",
    availability: "available",
    fromPrice: 9.8,
    sourcingCount: 5,
    aliases: ["albuterol", "puffer", "ventoline"]
  },
  {
    id: "nexium-40",
    brand: "Nexium",
    strength: "40mg",
    generic: "Esomeprazole",
    form: "Capsule",
    packSize: "14 capsules",
    manufacturer: "Astra",
    requiresPrescription: true,
    productType: "brand",
    availability: "available",
    fromPrice: 22.4,
    sourcingCount: 5,
    aliases: ["esomeprazol"]
  },
  {
    id: "zyrtec-10",
    brand: "Zyrtec",
    strength: "10mg",
    generic: "Cetirizine",
    form: "Tablet",
    packSize: "20 tablets",
    manufacturer: "UCB",
    requiresPrescription: false,
    productType: "brand",
    availability: "available",
    fromPrice: 5.6,
    sourcingCount: 8,
    aliases: ["cetirizin", "antihistamine"]
  },
  {
    id: "glucophage-850",
    brand: "Glucophage",
    strength: "850mg",
    generic: "Metformin",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Merck Santé",
    requiresPrescription: true,
    productType: "brand",
    availability: "limited",
    fromPrice: 4.95,
    sourcingCount: 3,
    aliases: ["metformine"]
  },
  {
    id: "voltaren-emulgel",
    brand: "Voltaren Emulgel",
    strength: "1%",
    generic: "Diclofenac",
    form: "Gel",
    packSize: "100g tube",
    manufacturer: "Novartis",
    requiresPrescription: false,
    productType: "brand",
    availability: "available",
    fromPrice: 10.2,
    sourcingCount: 7,
    aliases: ["voltarene", "diclofenac gel"]
  },
  {
    id: "concor-5",
    brand: "Concor",
    strength: "5mg",
    generic: "Bisoprolol",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Merck",
    requiresPrescription: true,
    productType: "brand",
    availability: "unavailable",
    fromPrice: null,
    sourcingCount: 0,
    aliases: ["bisoprolol fumarate"]
  },
  {
    id: "brufen-400",
    brand: "Brufen",
    strength: "400mg",
    generic: "Ibuprofen",
    form: "Tablet",
    packSize: "30 tablets",
    manufacturer: "Abbott",
    requiresPrescription: false,
    productType: "brand",
    availability: "available",
    fromPrice: 4.15,
    sourcingCount: 9,
    aliases: ["ibuprofene", "advil"]
  },
  {
    id: "zithromax-500",
    brand: "Zithromax",
    strength: "500mg",
    generic: "Azithromycin",
    form: "Tablet",
    packSize: "3 tablets",
    manufacturer: "Pfizer",
    requiresPrescription: true,
    productType: "brand",
    availability: "available",
    fromPrice: 16.4,
    sourcingCount: 5,
    aliases: ["azithromycine", "zitromax"]
  }
];

/**
 * Prompts for the empty search screen.
 *
 * Search *terms*, not results: the empty state has not asked any pharmacy
 * anything yet, so it must not imply that these are available.
 */
export const COMMON_SEARCH_TERMS = ["Panadol", "Augmentin", "Paracetamol", "Ventolin", "Atorvastatin", "Ibuprofen"];
