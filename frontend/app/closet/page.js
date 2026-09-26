"use client"; // runs in the browser (uses state + fetches data)

import { useEffect, useState } from "react";
import Link from "next/link";

const CLOSET_URL = "http://localhost:8080/closet";

export default function Closet() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // useEffect runs once when the page loads → fetch the closet from the backend.
  useEffect(() => {
    fetch(CLOSET_URL)
      .then((r) => r.json())
      .then((d) => setItems(d.items || []))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-5xl p-6">
      {/* navy header bar with a teal back-button */}
      <div className="mb-6 flex items-center justify-between rounded-2xl bg-[#0B2447] px-6 py-4 text-white">
        <div>
          <h1 className="text-xl font-semibold">My Closet</h1>
          <p className="text-sm text-slate-300">{items.length} items</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/wear-log"
            className="rounded-lg bg-white/10 px-4 py-2 text-sm font-medium hover:bg-white/20"
          >
            Wear log
          </Link>
          <Link
            href="/"
            className="rounded-lg bg-[#14B8A6] px-4 py-2 text-sm font-medium hover:bg-[#0E9384]"
          >
            ← Back to chat
          </Link>
        </div>
      </div>

      {loading && <p className="text-white">Loading your closet…</p>}
      {error && (
        <p className="rounded-lg bg-red-100 px-4 py-2 text-red-700">
          ⚠️ Couldn&apos;t reach the backend on :8080. Is uvicorn running?
        </p>
      )}

      {/* a responsive grid of clothing cards (one per item) */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
        {items.map((it) => (
          <div key={it.id} className="overflow-hidden rounded-xl border border-slate-300 bg-white shadow-sm">
            <div className="flex h-40 items-center justify-center bg-slate-100">
              {it.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={it.image_url} alt={it.name} className="h-full w-full object-cover" />
              ) : (
                <span className="text-sm text-slate-400">no photo</span>
              )}
            </div>
            <div className="p-3">
              <p className="font-medium text-slate-800">{it.name}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {it.category} · {it.color || "—"} · {it.warmth_level}
              </p>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
