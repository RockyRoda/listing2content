"use client";

import { LISTING_FIELDS, type ListingValues } from "@/lib/listingFields";

/** Renders the listing input grid, driven by LISTING_FIELDS. */
export default function ListingFields({
  values,
  onChange,
}: {
  values: ListingValues;
  onChange: (name: string, value: string) => void;
}) {
  return (
    <div className="form-grid">
      {LISTING_FIELDS.map((f) => (
        <div
          key={f.name}
          className={f.type === "textarea" ? "field field--wide" : "field"}
        >
          <label htmlFor={f.name}>
            {f.label}
            {f.required ? " *" : ""}
          </label>
          {f.type === "textarea" ? (
            <textarea
              id={f.name}
              rows={3}
              placeholder={f.placeholder}
              value={values[f.name]}
              onChange={(e) => onChange(f.name, e.target.value)}
            />
          ) : (
            <input
              id={f.name}
              type={f.type}
              step={f.step}
              required={f.required}
              placeholder={f.placeholder}
              value={values[f.name]}
              onChange={(e) => onChange(f.name, e.target.value)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
