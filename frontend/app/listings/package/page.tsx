"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { useObjectUrls } from "@/lib/useObjectUrls";
import AppHeader from "@/components/AppHeader";

type Slide = {
  id: number;
  listing_photo_id: number | null;
  order_index: number;
  caption: string;
  photo_url: string | null;
};
type Caption = { id: number; label: string; text: string };
type Package = {
  id: number;
  status: string;
  generated_at: string;
  reel_script: string;
  slides: Slide[];
  captions: Caption[];
};

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

  // Slides carry their own protected photo URL; key the blobs by slide id.
  const slideImages = useMemo(
    () =>
      (pkg?.slides ?? [])
        .filter((s) => s.photo_url)
        .map((s) => ({ id: s.id, url: s.photo_url as string })),
    [pkg],
  );
  const urls = useObjectUrls(slideImages);

  async function generate() {
    setBusy(true);
    setStatus("Reading the photos and writing the package...");
    const res = await api(`/listings/${id}/package`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setPkg(await res.json());
      setStatus("Draft ready.");
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
          <button className="btn btn--inline" onClick={generate} disabled={busy}>
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
          <>
            <section className="package-section">
              <div className="package-section__head">
                <h2>Carousel</h2>
                <span className="muted">
                  {pkg.slides.length} slide{pkg.slides.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="slide-grid">
                {pkg.slides.map((slide, i) => (
                  <figure className="slide" key={slide.id}>
                    <div className="photo">
                      {urls[slide.id] ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={urls[slide.id]} alt={`Slide ${i + 1}`} />
                      ) : (
                        <div className="photo__loading" />
                      )}
                    </div>
                    <figcaption>
                      <span className="slide__number">{i + 1}</span> {slide.caption}
                    </figcaption>
                  </figure>
                ))}
              </div>
            </section>

            <section className="package-section">
              <div className="package-section__head">
                <h2>Captions</h2>
              </div>
              <ul className="caption-list">
                {pkg.captions.map((caption) => (
                  <li className="caption-card" key={caption.id}>
                    <p className="eyebrow">{caption.label}</p>
                    <p>{caption.text}</p>
                  </li>
                ))}
              </ul>
            </section>

            <section className="package-section">
              <div className="package-section__head">
                <h2>Reel script</h2>
                <span className="muted">Draft generated {pkg.generated_at}</span>
              </div>
              <div className="sample-text">{pkg.reel_script}</div>
            </section>
          </>
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
