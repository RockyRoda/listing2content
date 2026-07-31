"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/auth";

export type ChatMessage = {
  id: number;
  role: string;
  content: string;
  created_at: string;
};

/** What the turn changed, so the host page reloads only what it owns. */
export type Applied = { listing: boolean; package: boolean };

/**
 * The listing's assistant: it records specs the agent mentions and rewrites
 * copy in the generated package on request.
 *
 * The transcript lives on the server, so this loads it rather than holding a
 * conversation the backend cannot see. A turn can change the listing or the
 * package underneath the page hosting this, hence onApplied.
 */
export default function ChatPanel({
  listingId,
  placeholder,
  onApplied,
}: {
  listingId: string;
  placeholder: string;
  onApplied: (applied: Applied) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const log = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const res = await api(`/listings/${listingId}/chat`);
    if (res.ok) setMessages(await res.json());
  }, [listingId]);

  useEffect(() => {
    load();
  }, [load]);

  // Follow the conversation as it grows, the way a chat is expected to behave.
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = draft.trim();
    if (!message) return;

    setBusy(true);
    setError("");
    const res = await api(`/listings/${listingId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    setBusy(false);

    if (!res.ok) {
      setError("The assistant did not respond. Try again.");
      return;
    }
    const body = await res.json();
    setMessages(body.messages);
    setDraft("");
    onApplied({ listing: body.listing_changed, package: body.package_changed });
  }

  return (
    <section className="chat">
      <div className="package-section__head">
        <h2>Assistant</h2>
        <span className="muted">Tell it a detail, or ask it to rewrite something</span>
      </div>

      <div className="chat__log" ref={log} role="log" aria-label="Conversation">
        {messages.length === 0 ? (
          <p className="muted chat__empty">
            Nothing yet. Describe the property in your own words, or ask for a change
            to the copy.
          </p>
        ) : (
          messages.map((m) => (
            <p className={`chat__msg chat__msg--${m.role}`} key={m.id}>
              {m.content}
            </p>
          ))
        )}
        {busy && <p className="chat__msg chat__msg--pending">Thinking...</p>}
      </div>

      <form className="chat__form" onSubmit={send}>
        <input
          type="text"
          aria-label="Message the assistant"
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn--inline" type="submit" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </section>
  );
}
