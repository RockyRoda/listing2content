"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import AppHeader from "@/components/AppHeader";
import PackageEditor, { type Package } from "@/components/PackageEditor";

const GENERATE_ERRORS: Record<number, string> = {
  400: "Add at least one photo to this listing first.",
  502: "The AI service did not respond. Try again.",
};

function PackageBody() {
  const user = useRequireAuth();
  const params = useSearchParams();
  const id = params.get("id");

  const [title, setTitle] = useState<string | null>(null);
  const [pkg, setPkg] = useState<Package | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    const listing = await api(`/listings/${id}`);
    if (!listing.ok) {
      setNotFound(true);
      return;
    }
    setTitle((await listing.json()).title);
    // A 404 here means no package has been generated yet, not a missing listing.
    const res = await api(`/listings/${id}/package`);
    setPkg(res.ok ? await res.json() : null);
  }, [id]);

  useEffect(() => {
    if (user && id) load();
  }, [user, id, load]);

  async function generate() {
    setBusy(true);
    setStatus("Reading the photos and writing the package...");
    const res = await api(`/listings/${id}/package`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setPkg(await res.json());
      setStatus("Draft ready. Edit anything below, then approve.");
    } else {
      setStatus(GENERATE_ERRORS[res.status] ?? "Could not generate the package.");
    }
  }

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
  if (title === null) return <div className="center-note">Loading package...</div>;

  return (
    <>
      <AppHeader />
      <main className="page">
        <p className="eyebrow">
          <Link href="/listings">Listings</Link> /{" "}
          <Link href={`/listings/detail?id=${id}`}>Edit</Link> / Package
        </p>
        <h1>{title}</h1>

        <div className="actions">
          <button className="btn btn--ghost btn--inline" onClick={generate} disabled={busy}>
            {busy ? "Generating..." : pkg ? "Regenerate" : "Generate package"}
          </button>
          <span className="muted" role="status">
            {status}
          </span>
        </div>

        {!pkg ? (
          <p className="muted">
            No package yet. Generation reads this listing&apos;s photos and specs, then
            drafts a carousel, caption set, and Reel script in your voice.
          </p>
        ) : (
          // Keyed on the package: regenerating replaces the draft, so the
          // editor remounts rather than carrying edits over to new copy.
          <PackageEditor key={pkg.id} listingId={id as string} initial={pkg} />
        )}
      </main>
    </>
  );
}

export default function PackagePage() {
  return (
    <Suspense fallback={<div className="center-note">Loading...</div>}>
      <PackageBody />
    </Suspense>
  );
}
