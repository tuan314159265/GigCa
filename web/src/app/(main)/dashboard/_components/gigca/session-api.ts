import { api, GigcaApiError } from "./api";
import type { DriverInput, Recommendation } from "./types";
type Session = { session_id: string; context_version: number };
let session: Session | null = null;
let queue: Promise<unknown> = Promise.resolve();
export function calculate(input: DriverInput): Promise<Recommendation> {
  const task = queue
    .catch(() => {})
    .then(async () => {
      try {
        if (input.mode === "research") {
          return await api<Recommendation>("/api/v1/research/recommendations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              driver_id: input.research_driver_id,
              context: input.context,
              rain_tolerance_level: input.rain_tolerance_level,
            }),
          });
        }
        if (!session)
          session = await api<Session>("/api/v1/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
        // The Next.js API proxy attaches the HttpOnly account cookie on the server.
        const headers = { "Content-Type": "application/json" };
        const updated = await api<{ context_version: number }>(`/api/v1/sessions/${session.session_id}/context`, {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            ...input.context,
            rain_tolerance_level: input.rain_tolerance_level,
            context_version: session.context_version,
          }),
        });
        session.context_version = updated.context_version;
        return await api<Recommendation>("/api/v1/recommendations", {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({ session_id: session.session_id, context_version: session.context_version }),
        });
      } catch (error) {
        session = null;
        if (error instanceof GigcaApiError && error.status === 401) window.location.replace("/auth/login");
        throw error;
      }
    });
  queue = task;
  return task;
}
