"use client";
// Wraps the app so client components can read the login session via useSession().
import { SessionProvider } from "next-auth/react";

export default function Providers({ children }) {
  return <SessionProvider>{children}</SessionProvider>;
}
