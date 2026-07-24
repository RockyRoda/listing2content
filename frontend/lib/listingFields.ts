/** Listing form fields, shared by the create and edit pages. */

export type FieldDef = {
  name: string;
  label: string;
  type: "text" | "number" | "textarea";
  required?: boolean;
  step?: string;
  placeholder?: string;
};

export const LISTING_FIELDS: FieldDef[] = [
  { name: "title", label: "Title", type: "text", required: true, placeholder: "Oceanfront Villa" },
  { name: "location", label: "Location", type: "text", placeholder: "Wailea, Maui" },
  { name: "price", label: "Price (USD)", type: "number", placeholder: "4500000" },
  { name: "beds", label: "Beds", type: "number" },
  { name: "baths", label: "Baths", type: "number", step: "0.5" },
  { name: "interior_sqft", label: "Interior sq ft", type: "number" },
  { name: "lot_size", label: "Lot size", type: "text", placeholder: "0.75 acres" },
  { name: "property_type", label: "Property type", type: "text", placeholder: "Single-family" },
  { name: "mls_number", label: "MLS number", type: "text" },
  { name: "features", label: "Features", type: "textarea", placeholder: "Infinity pool, chef's kitchen, ocean views" },
  { name: "description", label: "Description", type: "textarea" },
];

const NUMERIC = new Set(["price", "beds", "baths", "interior_sqft"]);

export type ListingValues = Record<string, string>;

/** Empty string values for every field. */
export function emptyValues(): ListingValues {
  return Object.fromEntries(LISTING_FIELDS.map((f) => [f.name, ""]));
}

/** Turn a loaded listing (mixed types) into string form values. */
export function valuesFrom(listing: Record<string, unknown>): ListingValues {
  const out = emptyValues();
  for (const f of LISTING_FIELDS) {
    const v = listing[f.name];
    out[f.name] = v === null || v === undefined ? "" : String(v);
  }
  return out;
}

/** Build the API payload, dropping empty fields and coercing numbers. */
export function toPayload(values: ListingValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of LISTING_FIELDS) {
    const v = (values[f.name] ?? "").trim();
    if (v === "") continue;
    out[f.name] = NUMERIC.has(f.name) ? Number(v) : v;
  }
  return out;
}
