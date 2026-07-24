"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { emptyValues, toPayload } from "@/lib/listingFields";
import AppHeader from "@/components/AppHeader";
import ListingFields from "@/components/ListingFields";

export default function NewListingPage() {
  const user = useRequireAuth();
  const router = useRouter();
  const [values, setValues] = useState(emptyValues());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  if (!user) return <div className="center-note">Loading...</div>;

  function set(name: string, value: string) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const res = await api("/listings", {
        method: "POST",
        body: JSON.stringify(toPayload(values)),
      });
      if (!res.ok) {
        setError("Could not create the listing. Check the fields and try again.");
        return;
      }
      const listing = await res.json();
      router.replace(`/listings/detail?id=${listing.id}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <AppHeader />
      <main className="page">
        <p className="eyebrow">New listing</p>
        <h1>Add a property</h1>
        <p className="muted">Only a title is required. Add photos after saving.</p>

        <form onSubmit={submit}>
          <ListingFields values={values} onChange={set} />
          <p className="form-error" role="alert">
            {error}
          </p>
          <div className="actions">
            <button className="btn btn--inline" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Create listing"}
            </button>
          </div>
        </form>
      </main>
    </>
  );
}
