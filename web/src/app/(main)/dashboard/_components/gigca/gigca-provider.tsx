"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { initialInput, type DriverInput, type Recommendation } from "./types";
import { previewOnly, previewRecommendation } from "./preview";
import { api } from "./api";
import { calculate } from "./session-api";
type State = {
  input: DriverInput;
  result: Recommendation | null;
  busy: boolean;
  error: string;
  tomtom: boolean;
  database: boolean;
  run: (input: DriverInput) => Promise<boolean>;
  retry: () => Promise<boolean>;
};
const Context = createContext<State | null>(null);
export function GigcaProvider({ children }: { children: ReactNode }) {
  const [input, setInput] = useState<DriverInput>(
    previewOnly
      ? initialInput
      : {
          ...initialInput,
          context: {
            ...initialInput.context,
            idle_duration_min: 15,
            horizon_min: 60,
            current_lat: NaN,
            current_lng: NaN,
          },
        },
  );
  const [result, setResult] = useState<Recommendation | null>(previewOnly ? previewRecommendation : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [database, setDatabase] = useState(false);
  const [tomtom, setTomtom] = useState(false);
  const requestId = useRef(0);
  const lastRequested = useRef(input);
  const run = useCallback(async (next: DriverInput) => {
    if (previewOnly) return false;
    lastRequested.current = next;
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    try {
      const data = await calculate(next);
      if (id === requestId.current) {
        setResult(data);
        setInput(next);
        return true;
      }
    } catch (e) {
      if (id === requestId.current) setError(e instanceof Error ? e.message : "API unavailable");
    } finally {
      if (id === requestId.current) setBusy(false);
    }
    return false;
  }, []);
  const retry = useCallback(() => run(lastRequested.current), [run]);
  useEffect(() => {
    if (previewOnly) return;
    const controller = new AbortController();
    void api<{ tomtom: boolean; database: boolean }>("/api/capabilities", {
      signal: controller.signal,
    })
      .then((x) => {
        setTomtom(x.tomtom);
        setDatabase(x.database);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (previewOnly || !result || !Number.isFinite(input.context.current_lat)) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void run(input);
    }, 60000);
    return () => window.clearInterval(timer);
  }, [input, run, Boolean(result)]);
  return (
    <Context.Provider value={{ input, result, busy, error, tomtom, database, run, retry }}>{children}</Context.Provider>
  );
}
// Shared input/result must survive navigation between the four dashboard pages.
// eslint-disable-next-line react-refresh/only-export-components
export function useGigca() {
  const state = useContext(Context);
  if (!state) throw new Error("Missing GigcaProvider");
  return state;
}
