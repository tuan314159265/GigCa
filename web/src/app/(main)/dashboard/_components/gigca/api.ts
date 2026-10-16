export class GigcaApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    signal: options?.signal ?? AbortSignal.timeout(45000),
  });
  const body = await response.json();
  if (!response.ok) throw new GigcaApiError((typeof body.error === "string" ? body.error : body.error?.message) || `HTTP ${response.status}`, response.status);
  return body;
}
