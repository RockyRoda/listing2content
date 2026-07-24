"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, getAuth, setAuth, type Auth } from "@/lib/auth";
import Wordmark from "./Wordmark";

type Mode = "signin" | "signup";

const COPY: Record<Mode, { heading: string; sub: string; cta: string }> = {
  signin: {
    heading: "Welcome back",
    sub: "Sign in to your content studio.",
    cta: "Sign in",
  },
  signup: {
    heading: "Create your studio",
    sub: "Turn a new listing into a full content package, in your voice.",
    cta: "Create studio",
  },
};

/** Shared sign in / sign up card. On success it stores {user, token} and
 *  lands on the dashboard. */
export default function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Already signed in? Skip the form.
  useEffect(() => {
    if (getAuth()) router.replace("/dashboard");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        setError(await messageFor(res, mode));
        return;
      }
      setAuth((await res.json()) as Auth);
      router.replace("/dashboard");
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setLoading(false);
    }
  }

  const copy = COPY[mode];

  return (
    <main className="auth-shell">
      <section className="card">
        <div className="card__head">
          <Wordmark />
          <hr className="horizon" />
          <h1>{copy.heading}</h1>
          <p className="card__sub">{copy.sub}</p>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="agent@studio.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              placeholder="Your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <p className="form-error" role="alert">
            {error}
          </p>

          <button className="btn" type="submit" disabled={loading}>
            {loading ? "One moment..." : copy.cta}
          </button>
        </form>

        <p className="card__foot">
          {mode === "signin" ? (
            <>
              New here? <Link href="/signup">Create your studio</Link>
            </>
          ) : (
            <>
              Already have an account? <Link href="/signin">Sign in</Link>
            </>
          )}
        </p>
      </section>
    </main>
  );
}

/** Turn an error response into a message the agent can act on. */
async function messageFor(res: Response, mode: Mode): Promise<string> {
  if (res.status === 422) return "Enter a valid email and password.";
  if (res.status === 409) return "That email is already registered. Sign in instead.";
  if (res.status === 401) return "Invalid email or password.";
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* fall through */
  }
  return mode === "signup" ? "Could not create your studio." : "Could not sign in.";
}
