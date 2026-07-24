"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import AppHeader from "@/components/AppHeader";

type Summary = {
  id: number;
  title: string;
  location: string | null;
  price: number | null;
  photo_count: number;
};

function money(price: number | null): string {
  if (price === null) return "";
  return "$" + price.toLocaleString("en-US");
}

export default function ListingsPage() {
  const user = useRequireAuth();
  const [listings, setListings] = useState<Summary[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api("/listings").then(async (res) => {
      if (res.ok) setListings(await res.json());
    });
  }, [user]);

  if (!user) return <div className="center-note">Loading...</div>;

  return (
    <>
      <AppHeader />
      <main className="page">
        <div className="page__head">
          <div>
            <p className="eyebrow">Listings</p>
            <h1>Your properties</h1>
          </div>
          <Link className="btn btn--inline" href="/listings/new">
            New listing
          </Link>
        </div>

        {listings === null ? (
          <p className="muted">Loading listings...</p>
        ) : listings.length === 0 ? (
          <p className="muted">No listings yet. Create your first to get started.</p>
        ) : (
          <ul className="listing-list">
            {listings.map((l) => (
              <li key={l.id}>
                <Link className="listing-card" href={`/listings/detail?id=${l.id}`}>
                  <div>
                    <h3>{l.title}</h3>
                    <p className="muted">{l.location || "Location not set"}</p>
                  </div>
                  <div className="listing-card__meta">
                    <span className="price">{money(l.price)}</span>
                    <span className="muted">
                      {l.photo_count} photo{l.photo_count === 1 ? "" : "s"}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
