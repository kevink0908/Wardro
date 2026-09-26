// auth.js — the central Auth.js (NextAuth v5) config.
// It reads AUTH_SECRET, AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET from .env.local automatically.
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google],
  trustHost: true, // allow localhost during local dev
});
