import "server-only";

import { cookies } from "next/headers";

import { AUTH_COOKIE, type Driver } from "@/lib/auth";

export async function currentDriver(): Promise<Driver | null> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return null;
  try {
    const backend = process.env.GIGCA_API_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${backend}/api/v1/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    return response.ok ? (await response.json()) as Driver : null;
  } catch {
    return null;
  }
}
