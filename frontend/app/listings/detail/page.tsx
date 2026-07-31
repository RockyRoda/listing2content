"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { toPayload, valuesFrom, type ListingValues } from "@/lib/listingFields";
import AppHeader from "@/components/AppHeader";
import ChatPanel, { type Applied } from "@/components/ChatPanel";
import ListingFields from "@/components/ListingFields";
import PhotoManager, { type Photo } from "@/components/PhotoManager";

type Listing = { id: number; title: string; photos: Photo[] } & Record<string, unknown>;

function DetailBody() {
  const user = useRequireAuth();
  const params = useSearchParams();
  const id = params.get("id");

  const [listing, setListing] = useState<Listing | null>(null);
  const [values, setValues] = useState<ListingValues | null>(null);
  const [status, setStatus] = useState("");
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    const res = await api(`/listings/${id}`);
    if (res.ok) {
      const data: Listing = await res.json();
      setListing(data);
      setValues(valuesFrom(data));
    } else {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => {
    if (user && id) load();
  }, [user, id, load]);

  if (!user) return <div className="center-note">Loading...</div>;
  if (notFound) {
    return (
      <>
        <AppHeader />
        <main className="page">
          <h1>Listing not found</h1>
          <p className="muted">
            It may have been removed. <Link href="/listings">Back to listings</Link>.
          </p>
        </main>
      </>
    );
  }
  if (!listing || !values) return <div className="center-note">Loading listing...</div>;

  function set(name: string, value: string) {
    setValues((v) => ({ ...(v as ListingValues), [name]: value }));
    setStatus("");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Saving...");
    const res = await api(`/listings/${id}`, {
      method: "PUT",
      body: JSON.stringify(toPayload(values as ListingValues)),
    });
    setStatus(res.ok ? "Saved." : "Could not save changes.");
    if (res.ok) load();
  }

  return (
    <>
      <AppHeader />
      <main className="page">
        <p className="eyebrow">
          <Link href="/listings">Listings</Link> / Edit
        </p>
        <h1>{listing.title}</h1>
        <p className="hint">
          <Link href={`/listings/package?id=${id}`}>Content package</Link>
        </p>

        <form onSubmit={save}>
          <ListingFields values={values} onChange={set} />
          <div className="actions">
            <button className="btn btn--inline" type="submit">
              Save changes
            </button>
            <span className="muted" role="status">
              {status}
            </span>
          </div>
        </form>

        <PhotoManager listingId={listing.id} photos={listing.photos} onChanged={load} />

        <ChatPanel
          listingId={id as string}
          placeholder="Four beds, 4.5 baths, asking $8.95M"
          // Reloading rebuilds the form from the server, so a field the
          // assistant just filled in shows up without a manual refresh.
          onApplied={(applied: Applied) => {
            if (applied.listing) {
              load();
              setStatus("The assistant updated this listing - form refreshed.");
            }
          }}
        />
      </main>
    </>
  );
}

export default function ListingDetailPage() {
  return (
    <Suspense fallback={<div className="center-note">Loading...</div>}>
      <DetailBody />
    </Suspense>
  );
}
