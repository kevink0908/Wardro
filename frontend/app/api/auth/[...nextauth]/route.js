// This file creates the login endpoints Google redirects back to
// (e.g. /api/auth/callback/google). Auth.js generates them from `handlers`.
import { handlers } from "@/auth";

export const { GET, POST } = handlers;
