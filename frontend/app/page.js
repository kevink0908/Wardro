"use client"; // chat client/frontend UI; Next.js + React app ran using "npm run dev"

import { useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown"; // turns the agent's **bold** / ### headings / * bullets into real formatting
import remarkGfm from "remark-gfm";         // adds GitHub-style tables, strikethrough, task lists
import { useSession, signIn, signOut } from "next-auth/react";

// The one line that points at your FastAPI backend (same endpoint as chat.html).
const BACKEND_URL = "http://localhost:8080/chat";

export default function Home() {
  // ── STATE: React's version of memory. When these change, React re-draws the UI. ──
  // messages = the whole conversation. input = what's in the text box. loading = waiting?
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: 'Hi! I\'m Wardro. Ask me what to wear and I\'ll check the weather and your closet. Try: "What should I wear today in San Jose?"',
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const { data: session } = useSession(); // the logged-in Google user (or null if signed out)

  async function sendMessage(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    // add the user's message to state, clear the box, show the spinner
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      // ── THE SAME fetch to /chat you used in chat.html and in /docs ──
      // POST { message } → wait → read { reply } back.
      const res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json(); // backend returns { reply: "..." }
      setMessages((prev) => [...prev, { role: "bot", text: data.reply }]);
    } catch (err) {
      // Distinguish "backend WAS reached but returned an error" from "couldn't connect at all".
      const text = String(err.message).startsWith("HTTP")
        ? "⚠️ The backend returned an error (" + err.message + "). Check the uvicorn terminal."
        : "⚠️ Couldn't reach the backend on :8080. Is uvicorn running?";
      setMessages((prev) => [...prev, { role: "error", text }]);
    } finally {
      setLoading(false);
    }
  }

  // ── UI: everything below is JSX (HTML-like syntax). className = Tailwind styling. ──
  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col border-x border-stone-200 bg-white">
      <header className="flex items-center justify-between bg-[#0B2447] px-6 py-4 text-white">
        <div>
          <h1 className="text-xl font-semibold">Wardro</h1>
          <p className="text-sm text-slate-300">Your AI styling agent</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/wear-log"
            className="rounded-lg bg-white/10 px-4 py-2 text-sm font-medium hover:bg-white/20"
          >
            Wear log
          </Link>
          <Link
            href="/closet"
            className="rounded-lg bg-[#14B8A6] px-4 py-2 text-sm font-medium hover:bg-[#0E9384]"
          >
            My closet →
          </Link>
          {session ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-200">{session.user?.name}</span>
              <button
                onClick={() => signOut()}
                className="rounded-lg bg-white/10 px-3 py-2 text-sm hover:bg-white/20"
              >
                Sign out
              </button>
            </div>
          ) : (
            <button
              onClick={() => signIn("google")}
              className="rounded-lg border border-white/30 px-4 py-2 text-sm font-medium hover:bg-white/10"
            >
              Sign in with Google
            </button>
          )}
        </div>
      </header>

      {/* messages.map(...) draws one bubble per message — React's "list = UI" idea */}
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-[#0B2447] px-4 py-2.5 text-white"
                : m.role === "error"
                ? "max-w-[80%] rounded-2xl bg-red-100 px-4 py-2.5 text-red-700"
                : "max-w-[80%] rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-2.5 text-slate-800"
            }
          >
            {m.role === "bot" ? (
              // Gemini replies in markdown, so render it instead of showing raw ** and ###
              <div className="md leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
              </div>
            ) : (
              <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
            )}
          </div>
        ))}
        {loading && <p className="text-sm italic text-stone-400">thinking…</p>}
      </div>

      <form onSubmit={sendMessage} className="flex gap-2 border-t border-stone-200 p-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What should I wear today in…?"
          className="flex-1 rounded-xl border border-slate-300 px-4 py-3 outline-none focus:border-[#14B8A6]"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-xl bg-[#14B8A6] px-5 py-3 font-medium text-white hover:bg-[#0E9384] disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  );
}
