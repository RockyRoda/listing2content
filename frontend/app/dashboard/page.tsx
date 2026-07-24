"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearAuth, getAuth, type AuthUser } from "@/lib/auth";
import Wordmark from "@/components/Wordmark";

/** What the studio will hold once later phases land. */
const TILES = [
  {
    label: "Listing",
    title: "New listing",
    body: "Add specs, features, MLS details, and photos for a property.",
  },
  {
    label: "Voice",
    title: "Voice profile",
    body: "Upload writing samples so every draft sounds like you.",
  },
  {
    label: "Package",
    title: "Content packages",
    body: "Carousels, caption sets, and Reel scripts, ready to approve.",
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  // Client-side gate: confirm the stored token is still valid, else sign out.
  useEffect(() => {
    const auth = getAuth();
    if (!auth) {
      router.replace("/signin");
      return;
    }
    api("/auth/me").then((res) => {
      if (res.ok) {
        setUser(auth.user);
        setReady(true);
      } else {
        clearAuth();
        router.replace("/signin");
      }
    });
  }, [router]);

  function signOut() {
    clearAuth();
    router.replace("/signin");
  }

  if (!ready || !user) {
    return <div className="center-note">Opening your studio...</div>;
  }

  const name = user.email.split("@")[0];

  return (
    <>
      <header className="topbar">
        <Wordmark />
        <button className="btn btn--ghost" onClick={signOut}>
          Sign out
        </button>
      </header>
      <div className="topbar__divider">
        <hr className="horizon" />
      </div>

      <main className="dash">
        <section className="dash__hero">
          <p className="eyebrow">Your studio</p>
          <h1>
            Golden hour, <em>{name}</em>.
          </h1>
          <p>
            Your content studio is ready. Listings, voice profiles, and
            generation arrive in the next releases.
          </p>
        </section>

        <section className="tiles">
          {TILES.map((tile) => (
            <article className="tile" key={tile.title}>
              <span className="tile__index">{tile.label}</span>
              <h3>{tile.title}</h3>
              <p>{tile.body}</p>
              <span className="tile__tag">Coming soon</span>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
