"use client";

import { useEffect, useRef, useState } from "react";

import { ArrowRight, Bot, LoaderCircle, MessageCircle, Send, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { api } from "../../_components/gigca/api";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { directions } from "../../_components/gigca/labels";
import type { Objective, Recommendation } from "../../_components/gigca/types";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  suggested_objective?: Objective | null;
  provider?: string;
};
type ChatResponse = { reply: string; suggested_objective: Objective | null; provider: string };

const starters = ["Nên chọn hướng nào lúc này?", "Giải thích hướng đang chọn", "Mình muốn tránh mưa hơn"];

function recommendationContext(result: Recommendation) {
  return {
    objectives: Object.fromEntries(
      Object.entries(result.objectives).map(([key, value]) => [
        key,
        {
          status: value.status,
          confidence: value.confidence,
          plan: value.plan
            ? {
                summary: value.plan.summary,
                target_location: value.plan.target_location,
                trade_offs: value.plan.trade_offs,
                key_metrics: value.plan.key_metrics,
              }
            : null,
          caveat: value.caveat,
          reason_for_insufficiency: value.reason_for_insufficiency,
        },
      ]),
    ),
    data_quality_warnings: result.data_quality_warnings,
    snapshot: { mode: result.snapshot.mode, as_of: result.snapshot.as_of },
  };
}

export function DriverAssistant({ selected, onSelect }: { selected: Objective; onSelect: (key: Objective) => void }) {
  const { input, result } = useGigca();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  });

  async function send(text = draft) {
    const content = text.trim();
    if (!content || busy) return;
    setDraft("");
    setError("");
    const next = [...messages, { id: crypto.randomUUID(), role: "user" as const, content }];
    setMessages(next);
    setBusy(true);
    try {
      if (!result) throw new Error("Hãy tính gợi ý trước để trợ lý đọc được các dự báo hiện tại.");
      const response = await api<ChatResponse>("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: next.slice(-10).map(({ role, content: message }) => ({ role, content: message })),
          recommendation: recommendationContext(result),
          selected_objective: selected,
          driver_context: {
            idle_duration_min: input.context.idle_duration_min,
            horizon_min: input.context.horizon_min,
            max_reposition_km: input.context.max_reposition_km,
            rain_tolerance_level: input.rain_tolerance_level,
          },
        }),
      });
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.reply,
          suggested_objective: response.suggested_objective,
          provider: response.provider,
        },
      ]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Chưa gửi được tin nhắn. Thử lại nhé.");
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-[70] flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {open && (
        <section
          role="dialog"
          aria-label="Trợ lý AI GigCa"
          className="flex h-[min(38rem,calc(100dvh-7rem))] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl"
        >
          <header className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Sparkles className="size-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h2 className="font-semibold">Trợ lý GigCa</h2>
                <p className="truncate text-xs text-muted-foreground">Tư vấn theo dự báo hiện tại</p>
              </div>
            </div>
            <Button variant="ghost" size="icon" aria-label="Đóng trợ lý" onClick={() => setOpen(false)}>
              <X aria-hidden="true" />
            </Button>
          </header>

          <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4" aria-live="polite">
            <div className="max-w-[92%] self-start rounded-2xl rounded-tl-sm bg-muted px-3.5 py-3 text-sm">
              Mình sẽ dựa vào các dự báo về năng suất, thời gian chờ, vị trí và thời tiết để gợi ý hướng phù hợp. Bạn đang ưu tiên điều gì?
              {!result && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Tính gợi ý trước để mình đọc được các dự báo hiện tại.
                </p>
              )}
            </div>
            {messages.map((message) => {
              const suggestedObjective = message.suggested_objective;
              return (
                <div
                  key={message.id}
                  className={`flex flex-col gap-2 ${message.role === "user" ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-3.5 py-3 text-sm ${
                      message.role === "user"
                        ? "rounded-tr-sm bg-primary text-primary-foreground"
                        : "rounded-tl-sm bg-muted"
                    }`}
                  >
                    {message.content}
                  </div>
                  {message.role === "assistant" && message.provider && (
                    <span className="px-1 text-[11px] text-muted-foreground">
                      {message.provider === "prediction_advisor"
                        ? "Theo dự báo hiện tại"
                        : "AI tham khảo dự báo hiện tại"}
                    </span>
                  )}
                  {message.role === "assistant" && suggestedObjective && (
                    <Button size="sm" variant="outline" className="ml-1" onClick={() => onSelect(suggestedObjective)}>
                      Chọn {directions[suggestedObjective].title}
                      <ArrowRight data-icon="inline-end" />
                    </Button>
                  )}
                </div>
              );
            })}
            {busy && (
              <div className="flex items-center gap-2 self-start rounded-2xl bg-muted px-3.5 py-3 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                Đang xem ngữ cảnh…
              </div>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            {messages.length === 0 && (
              <div className="mt-1 flex flex-wrap gap-2">
                {starters.map((starter) => (
                  <Button
                    key={starter}
                    size="sm"
                    variant="outline"
                    disabled={busy || !result}
                    onClick={() => void send(starter)}
                  >
                    {starter}
                  </Button>
                ))}
              </div>
            )}
          </div>

          <form
            className="flex items-end gap-2 border-t p-3"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <Textarea
              ref={inputRef}
              rows={2}
              className="max-h-28 min-h-12 resize-none text-sm"
              placeholder={result ? "Hỏi về các hướng gợi ý…" : "Tính gợi ý trước nhé"}
              value={draft}
              maxLength={1200}
              disabled={busy || !result}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              aria-label="Tin nhắn cho trợ lý"
            />
            <Button type="submit" size="icon" aria-label="Gửi tin nhắn" disabled={busy || !result || !draft.trim()}>
              <Send aria-hidden="true" />
            </Button>
          </form>
          <p className="px-3 pb-2 text-center text-[11px] text-muted-foreground">
            Trợ lý tham khảo dữ liệu Engine; bạn quyết định hướng cuối cùng.
          </p>
        </section>
      )}
      <Button
        className="relative size-14 rounded-full shadow-lg"
        size="icon"
        aria-label={open ? "Đóng trợ lý GigCa" : "Mở trợ lý GigCa"}
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value);
          if (!open) requestAnimationFrame(() => inputRef.current?.focus());
        }}
      >
        {open ? (
          <X aria-hidden="true" />
        ) : (
          <>
            <MessageCircle aria-hidden="true" />
            <Bot
              className="absolute size-4 translate-x-2.5 translate-y-2.5 rounded-full bg-primary p-0.5"
              aria-hidden="true"
            />
          </>
        )}
      </Button>
    </div>
  );
}
