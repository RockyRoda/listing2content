"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiObjectUrl, apiUpload } from "@/lib/auth";

export type Photo = {
  id: number;
  original_name: string | null;
  content_type: string;
  url: string;
};

const UPLOAD_ERRORS: Record<number, string> = {
  413: "Each photo must be 5 MB or less.",
  415: "Photos must be JPEG, PNG, or WebP.",
  400: "A listing can hold at most 20 photos.",
};

/** Thumbnail grid with upload + delete for a listing's photos. */
export default function PhotoManager({
  listingId,
  photos,
  onChanged,
}: {
  listingId: number;
  photos: Photo[];
  onChanged: () => void;
}) {
  const [urls, setUrls] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Load each protected photo as an object URL; revoke them on change/unmount.
  useEffect(() => {
    let active = true;
    const made: string[] = [];
    Promise.all(
      photos.map(async (p) => [p.id, await apiObjectUrl(p.url)] as const),
    ).then((pairs) => {
      if (!active) return;
      const next: Record<number, string> = {};
      for (const [id, url] of pairs) {
        if (url) {
          next[id] = url;
          made.push(url);
        }
      }
      setUrls(next);
    });
    return () => {
      active = false;
      made.forEach(URL.revokeObjectURL);
    };
  }, [photos]);

  async function upload(files: FileList) {
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append("files", f));
      const res = await apiUpload(`/listings/${listingId}/photos`, form);
      if (!res.ok) {
        setError(UPLOAD_ERRORS[res.status] ?? "Could not upload the photos.");
        return;
      }
      onChanged();
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(photo: Photo) {
    setError("");
    const res = await api(photo.url, { method: "DELETE" });
    if (res.ok) onChanged();
    else setError("Could not delete the photo.");
  }

  return (
    <section className="photos">
      <div className="photos__head">
        <h2>Photos</h2>
        <label className="btn btn--ghost btn--inline">
          {busy ? "Uploading..." : "Add photos"}
          <input
            ref={fileInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            hidden
            disabled={busy}
            onChange={(e) => e.target.files && upload(e.target.files)}
          />
        </label>
      </div>

      <p className="form-error" role="alert">
        {error}
      </p>

      {photos.length === 0 ? (
        <p className="muted">No photos yet. Add JPEG, PNG, or WebP (up to 5 MB each).</p>
      ) : (
        <div className="photo-grid">
          {photos.map((p) => (
            <figure className="photo" key={p.id}>
              {urls[p.id] ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={urls[p.id]} alt={p.original_name ?? "Listing photo"} />
              ) : (
                <div className="photo__loading" />
              )}
              <button
                type="button"
                className="photo__remove"
                aria-label="Remove photo"
                onClick={() => remove(p)}
              >
                &times;
              </button>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
