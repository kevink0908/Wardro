"use client"; // runs in the browser (uses state + fetches data)

import { useEffect, useState } from "react";
import Link from "next/link";

const WEAR_LOG_URL = "http://localhost:8080/wear-log";

export default function WearLog() {
  const [entries, setEntries] = useState([]);
  const [counts, setCounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Fetch the wear log from the backend once, when the page loads.
  useEffect(() => {
    fetch(WEAR_LOG_URL)
      .then((r) => r.json())
      .then((d) => {
        setEntries(d.entries || []);
        setCounts(d.counts || []);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-5xl p-6">
      {/* navy header bar with a teal back-button (same style as /closet) */}
      <div className="mb-6 flex items-center justify-between rounded-2xl bg-[#0B2447] px-6 py-4 text-white">
        <div>
          <h1 className="text-xl font-semibold">Wear Log</h1>
          <p className="text-sm text-slate-300">
            {entries.length} entries · tell the chat &quot;I wore my black hoodie
            today for work&quot; to add one
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/closet"
            className="rounded-lg bg-white/10 px-4 py-2 text-sm font-medium hover:bg-white/20"
          >
            My closet
          </Link>
          <Link
            href="/"
            className="rounded-lg bg-[#14B8A6] px-4 py-2 text-sm font-medium hover:bg-[#0E9384]"
          >
            ← Back to chat
          </Link>
        </div>
      </div>

      {loading && <p className="text-white">Loading your wear log…</p>}
      {error && (
        <p className="rounded-lg bg-red-100 px-4 py-2 text-red-700">
          ⚠️ Couldn&apos;t reach the backend on :8080. Is uvicorn running?
        </p>
      )}

      {!loading && !error && (
        <div className="grid gap-6 md:grid-cols-2">
          {/* LEFT: recent wears, newest first */}
          <section className="rounded-xl border border-slate-300 bg-white shadow-sm">
            <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-800">
              Recent wears
            </h2>
            {entries.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">
                Nothing logged yet. Accept an outfit in the chat, or say
                &quot;I wore X yesterday&quot;.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {entries.map((e) => (
                  <li key={e.id} className="flex items-baseline justify-between px-4 py-2.5">
                    <div>
                      <p className="font-medium text-slate-800">{e.name}</p>
                      <p className="text-xs text-slate-500">
                        {e.worn_on}
                        {e.occasion && <> · <span className="text-[#0E9384]">{e.occasion}</span></>}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* RIGHT: per-item totals, least-worn first (what the packing agent uses) */}
          <section className="rounded-xl border border-slate-300 bg-white shadow-sm">
            <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-800">
              Times worn <span className="font-normal text-slate-400">(least first)</span>
            </h2>
            <ul className="divide-y divide-slate-100">
              {counts.map((c) => (
                <li key={c.item_id} className="flex items-center justify-between px-4 py-2.5">
                  <div>
                    <p className="font-medium text-slate-800">{c.name}</p>
                    <p className="text-xs text-slate-500">
                      {c.category} · {c.color || "—"}
                      {c.last_worn && <> · last worn {c.last_worn}</>}
                    </p>
                  </div>
                  <span
                    className={
                      "rounded-full px-2.5 py-0.5 text-sm font-semibold " +
                      (c.times_worn === 0
                        ? "bg-slate-100 text-slate-500"
                        : "bg-[#14B8A6]/15 text-[#0E9384]")
                    }
                  >
                    {c.times_worn}×
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}
