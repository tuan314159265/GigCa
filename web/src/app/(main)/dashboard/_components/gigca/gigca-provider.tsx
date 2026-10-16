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
  researchAvailable: boolean;
  capabilitiesError: string;
  initialize: () => void;
  run: (input: DriverInput) => Promise<boolean>;
  retry: () => Promise<boolean>;
};
const Context = createContext<State | null>(null);
export function GigcaProvider({ children }: { children: ReactNode }) {
  const [input, setInput] = useState<DriverInput>(initialInput);
  const [result, setResult] = useState<Recommendation | null>(previewOnly ? previewRecommendation : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [database, setDatabase] = useState(false);
  const [tomtom, setTomtom] = useState(false);
  const [researchAvailable, setResearchAvailable] = useState(false);
  const [capabilitiesError, setCapabilitiesError] = useState("");
  const initialized = useRef(false);
  const requestId = useRef(0);
  const lastRequested = useRef(input);
  const initialize = useCallback(() => {
    if (previewOnly || initialized.current) return;
    initialized.current = true;
    setInput((current) => ({
      ...current,
      context: { ...current.context, idle_duration_min: 15, horizon_min: 60, current_lat: NaN, current_lng: NaN },
    }));
    const controller = new AbortController();
    void api<{ tomtom: boolean; database: boolean; research_demo: boolean; data_mode: string }>("/api/capabilities", {
      signal: controller.signal,
    })
      .then((x) => {
        setTomtom(x.tomtom);
        setDatabase(x.database);
        setResearchAvailable(x.research_demo);
        setInput((current) => ({ ...current, mode: x.data_mode === "live" ? "live" : "sample" }));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setCapabilitiesError(error instanceof Error ? error.message : "Không đọc được cấu hình backend.");
      });
  }, []);
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
    if (previewOnly || input.mode === "research" || !result || !Number.isFinite(input.context.current_lat)) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void run(input);
    }, 60000);
    return () => window.clearInterval(timer);
  }, [input, run, Boolean(result)]);
  return (
    <Context.Provider
      value={{ input, result, busy, error, tomtom, database, researchAvailable, capabilitiesError, initialize, run, retry }}
    >
      {children}
    </Context.Provider>
  );
}
// Shared input/result must survive navigation between the four dashboard pages.
// eslint-disable-next-line react-refresh/only-export-components
export function useGigca() {
  const state = useContext(Context);
  if (!state) throw new Error("Missing GigcaProvider");
  return state;
}
