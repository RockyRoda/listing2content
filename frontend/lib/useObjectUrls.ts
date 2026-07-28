"use client";

import { useEffect, useState } from "react";
import { apiObjectUrl } from "./auth";

/**
 * Load protected API resources as object URLs, keyed by id. Photos need a
 * bearer token, so they cannot be set as a plain img src. Pass a stable array
 * (a prop, or a useMemo result) - the URLs are revoked when it changes.
 */
export function useObjectUrls(items: { id: number; url: string }[]): Record<number, string> {
  const [urls, setUrls] = useState<Record<number, string>>({});

  useEffect(() => {
    let active = true;
    const made: string[] = [];
    Promise.all(
      items.map(async (item) => [item.id, await apiObjectUrl(item.url)] as const),
    ).then((pairs) => {
      const loaded = pairs.filter(([, url]) => url !== null) as [number, string][];
      // The effect went stale while these were in flight, so cleanup has
      // already run on an empty list - revoke them here instead.
      if (!active) {
        loaded.forEach(([, url]) => URL.revokeObjectURL(url));
        return;
      }
      const next: Record<number, string> = {};
      for (const [id, url] of loaded) {
        next[id] = url;
        made.push(url);
      }
      setUrls(next);
    });
    return () => {
      active = false;
      made.forEach(URL.revokeObjectURL);
    };
  }, [items]);

  return urls;
}
