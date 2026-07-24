"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/auth";
import { useRequireAuth } from "@/lib/useRequireAuth";
import AppHeader from "@/components/AppHeader";

type Profile = { sample_text: string; tone_notes: string; updated_at: string | null };

export default function SettingsPage() {
  const user = useRequireAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [toneNotes, setToneNotes] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    const res = await api("/voice-profile");
    if (res.ok) {
      const data: Profile = await res.json();
      setProfile(data);
      setToneNotes(data.tone_notes);
    }
  }

  useEffect(() => {
    if (user) load();
  }, [user]);

  if (!user) return <div className="center-note">Loading...</div>;
  if (!profile) return <div className="center-note">Loading voice profile...</div>;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Saving...");
    setSaving(true);
    try {
      const form = new FormData();
      const files = fileInput.current?.files;
      if (files) Array.from(files).forEach((f) => form.append("files", f));
      form.append("tone_notes", toneNotes);
      const res = await apiUpload("/voice-profile", form, "PUT");
      if (!res.ok) {
        setStatus(res.status === 415 ? "Samples must be .txt files." : "Could not save.");
        return;
      }
      const data: Profile = await res.json();
      setProfile(data);
      setStatus("Saved.");
      if (fileInput.current) fileInput.current.value = "";
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <AppHeader />
      <main className="page">
        <p className="eyebrow">Voice profile</p>
        <h1>Sound like you</h1>
        <p className="muted">
          Upload writing samples (.txt) and add tone notes. Every generated draft
          uses these to match your voice.
        </p>

        <form onSubmit={save}>
          <div className="field field--wide">
            <label htmlFor="samples">Writing samples (.txt)</label>
            <input id="samples" ref={fileInput} type="file" accept=".txt,text/plain" multiple />
            <p className="hint">Uploading replaces the current samples.</p>
          </div>

          <div className="field field--wide">
            <label htmlFor="tone">Tone notes</label>
            <textarea
              id="tone"
              rows={3}
              placeholder="Warm, confident, understated luxury."
              value={toneNotes}
              onChange={(e) => setToneNotes(e.target.value)}
            />
          </div>

          <div className="actions">
            <button className="btn btn--inline" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save voice profile"}
            </button>
            <span className="muted" role="status">
              {status}
            </span>
          </div>
        </form>

        <section className="current-sample">
          <h2>Current samples</h2>
          {profile.updated_at && (
            <p className="muted">Updated {profile.updated_at} UTC</p>
          )}
          {profile.sample_text ? (
            <pre className="sample-text">{profile.sample_text}</pre>
          ) : (
            <p className="muted">No samples uploaded yet.</p>
          )}
        </section>
      </main>
    </>
  );
}
