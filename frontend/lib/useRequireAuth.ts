"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearAuth, getAuth, type AuthUser } from "./auth";

/**
 * Gate a client page on a valid session. Returns the user once confirmed, or
 * null while checking / redirecting. Verifies the stored token via /auth/me and
 * signs out on failure (e.g. after a server restart wiped the sessions table).
 */
export function useRequireAuth(): AuthUser | null {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const auth = getAuth();
    if (!auth) {
      router.replace("/signin");
      return;
    }
    api("/auth/me").then((res) => {
      if (res.ok) {
        setUser(auth.user);
      } else {
        clearAuth();
        router.replace("/signin");
      }
    });
  }, [router]);

  return user;
}
