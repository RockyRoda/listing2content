"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/auth";
import { useObjectUrls } from "@/lib/useObjectUrls";

export type Slide = {
  id: number;
  listing_photo_id: number | null;
  order_index: number;
  caption: string;
  photo_url: string | null;
};
export type Caption = { id: number; label: string; text: string };
export type Package = {
  id: number;
  status: string;
  generated_at: string;
  reel_script: string;
  slides: Slide[];
  captions: Caption[];
};

/**
 * The review pass: every piece of the draft is editable in place, saved in one
 * PUT, then approved. Saving returns the package to draft (approval covers the
 * exact copy), so Approve waits until there is nothing unsaved.
 *
 * Owns the package from mount on - the parent passes the generated draft as
 * `initial` and remounts this on regeneration by keying it on the package id.
 */
export default function PackageEditor({
  listingId,
  initial,
}: {
  listingId: string;
  initial: Package;
}) {
  const [pkg, setPkg] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  // Photo bindings are fixed for a package, so derive the images from the
  // unchanging `initial` copy - editing a caption must not refetch them.
  const images = useMemo(
    () =>
      initial.slides
        .filter((s) => s.photo_url)
        .map((s) => ({ id: s.id, url: s.photo_url as string })),
    [initial.slides],
  );
  const urls = useObjectUrls(images);

  function edited() {
    setDirty(true);
    setStatus("");
  }

  function editSlide(id: number, caption: string) {
    setPkg((p) => ({
      ...p,
      slides: p.slides.map((s) => (s.id === id ? { ...s, caption } : s)),
    }));
    edited();
  }

  function editCaption(id: number, text: string) {
    setPkg((p) => ({
      ...p,
      captions: p.captions.map((c) => (c.id === id ? { ...c, text } : c)),
    }));
    edited();
  }

  function editScript(reel_script: string) {
    setPkg((p) => ({ ...p, reel_script }));
    edited();
  }

  async function save() {
    setBusy(true);
    setStatus("Saving...");
    const res = await api(`/listings/${listingId}/package`, {
      method: "PUT",
      body: JSON.stringify({
        reel_script: pkg.reel_script,
        slides: pkg.slides.map(({ id, caption }) => ({ id, caption })),
        captions: pkg.captions.map(({ id, text }) => ({ id, text })),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setStatus("Could not save your edits.");
      return;
    }
    setPkg(await res.json());
    setDirty(false);
    setStatus("Saved.");
  }

  async function approve() {
    setBusy(true);
    setStatus("Approving...");
    const res = await api(`/listings/${listingId}/package/approve`, {
      method: "POST",
    });
    setBusy(false);
    if (!res.ok) {
      setStatus("Could not approve the package.");
      return;
    }
    setPkg(await res.json());
    setStatus("Approved.");
  }

  const approved = pkg.status === "approved";

  return (
    <>
      <div className="review-bar">
        <span className={approved ? "badge badge--approved" : "badge"}>
          {approved ? "Approved" : "Draft"}
        </span>
        <button className="btn btn--inline" onClick={save} disabled={busy || !dirty}>
          Save edits
        </button>
        <button
          className="btn btn--ghost btn--inline"
          onClick={approve}
          disabled={busy || dirty || approved}
        >
          Approve
        </button>
        <span className="muted" role="status">
          {dirty ? "Unsaved edits - save before approving." : status}
        </span>
      </div>

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
                <span className="slide__number">{i + 1}</span>
                <textarea
                  rows={4}
                  aria-label={`Slide ${i + 1} caption`}
                  value={slide.caption}
                  onChange={(e) => editSlide(slide.id, e.target.value)}
                />
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
              <label className="eyebrow" htmlFor={`caption-${caption.id}`}>
                {caption.label}
              </label>
              <textarea
                id={`caption-${caption.id}`}
                rows={3}
                value={caption.text}
                onChange={(e) => editCaption(caption.id, e.target.value)}
              />
            </li>
          ))}
        </ul>
      </section>

      <section className="package-section">
        <div className="package-section__head">
          <h2>Reel script</h2>
          <span className="muted">Generated {pkg.generated_at} UTC</span>
        </div>
        <textarea
          rows={12}
          aria-label="Reel script"
          value={pkg.reel_script}
          onChange={(e) => editScript(e.target.value)}
        />
      </section>
    </>
  );
}
