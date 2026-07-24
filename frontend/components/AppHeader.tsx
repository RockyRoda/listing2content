"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearAuth } from "@/lib/auth";
import Wordmark from "./Wordmark";

const NAV = [
  { href: "/dashboard", label: "Studio" },
  { href: "/listings", label: "Listings" },
  { href: "/settings", label: "Voice" },
];

/** Shared authenticated header: wordmark, section nav, and sign out. */
export default function AppHeader() {
  const router = useRouter();
  const pathname = usePathname();

  function signOut() {
    clearAuth();
    router.replace("/signin");
  }

  return (
    <>
      <header className="topbar">
        <Link href="/dashboard" aria-label="Listing2Content home">
          <Wordmark />
        </Link>
        <nav className="appnav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname.startsWith(item.href) ? "appnav__link is-active" : "appnav__link"}
            >
              {item.label}
            </Link>
          ))}
          <button className="btn btn--ghost" onClick={signOut}>
            Sign out
          </button>
        </nav>
      </header>
      <div className="topbar__divider">
        <hr className="horizon" />
      </div>
    </>
  );
}
