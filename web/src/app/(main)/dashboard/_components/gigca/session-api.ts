import { api } from "./api";
import type { DriverInput, Recommendation } from "./types";
type Session = { session_id: string; token: string; context_version: number };
let session: Session | null = null;
let queue: Promise<unknown> = Promise.resolve();
export function calculate(input: DriverInput): Promise<Recommendation> {
  const task = queue
    .catch(() => {})
    .then(async () => {
      if (!session)
        session = await api<Session>("/api/v1/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
      const headers = { "Content-Type": "application/json", Authorization: `Bearer ${session.token}` };
      try {
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
        throw error;
      }
    });
  queue = task;
  return task;
}
