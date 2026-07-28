"use client";

import Link from "next/link";
import { useRequireAuth } from "@/lib/useRequireAuth";
import AppHeader from "@/components/AppHeader";

/** The studio's sections. */
const TILES = [
  {
    label: "Listing",
    title: "New listing",
    body: "Add specs, features, MLS details, and photos for a property.",
    href: "/listings/new",
    cta: "Create",
  },
  {
    label: "Voice",
    title: "Voice profile",
    body: "Upload writing samples so every draft sounds like you.",
    href: "/settings",
    cta: "Edit",
  },
  {
    label: "Package",
    title: "Content packages",
    body: "Carousels, caption sets, and Reel scripts, ready to approve.",
    href: "/listings",
    cta: "Generate",
  },
];

export default function DashboardPage() {
  const user = useRequireAuth();
  if (!user) return <div className="center-note">Opening your studio...</div>;

  const name = user.email.split("@")[0];

  return (
    <>
      <AppHeader />
      <main className="dash">
        <section className="dash__hero">
          <p className="eyebrow">Your studio</p>
          <h1>
            Golden hour, <em>{name}</em>.
          </h1>
          <p>
            Add a listing and upload photos, set your voice profile, then
            generate a content package from any listing.
          </p>
        </section>

        <section className="tiles">
          {TILES.map((tile) => (
            <article className="tile" key={tile.title}>
              <span className="tile__index">{tile.label}</span>
              <h3>{tile.title}</h3>
              <p>{tile.body}</p>
              {tile.href ? (
                <Link className="tile__tag tile__tag--link" href={tile.href}>
                  {tile.cta}
                </Link>
              ) : (
                <span className="tile__tag">{tile.cta}</span>
              )}
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
