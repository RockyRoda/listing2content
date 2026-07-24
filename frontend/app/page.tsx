"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAuth } from "@/lib/auth";

/** Entry point: route to the studio when signed in, otherwise to sign in. */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getAuth() ? "/dashboard" : "/signin");
  }, [router]);

  return <div className="center-note">Loading...</div>;
}
