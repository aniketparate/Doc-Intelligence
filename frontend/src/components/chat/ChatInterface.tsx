"use client";

import clsx from "clsx";
import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useRef, useState } from "react";

import { ConfidenceBar } from "@/components/workspace/ConfidenceBar";
import { useChat } from "@/hooks/useChat";
import { ConfidenceBreakdown, RetrievalMode, SourceChunkResponse } from "@/lib/types";

import { MarkdownRenderer } from "./MarkdownRenderer";

export type WorkspaceMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  confidence: number | null;
  sources: SourceChunkResponse[];
  confidenceBreakdown?: ConfidenceBreakdown | null;
};

type ChatInterfaceProps = {
  projectId: string;
  sessionId: string | null;
  messages: WorkspaceMessage[];
  setMessages: Dispatch<SetStateAction<WorkspaceMessage[]>>;
  onSourcesSelect: (sources: SourceChunkResponse[]) => void;
  disabled?: boolean;
  isHistoryLoading?: boolean;
};

const SCROLL_BOTTOM_THRESHOLD = 140;

function normalizeConfidence(confidence: number | null): string {
  if (confidence === null || Number.isNaN(confidence)) return "N/A";
  return `${Math.round(confidence * 100)}%`;
}

function confidenceClass(confidence: number | null): string {
  if (confidence === null || Number.isNaN(confidence)) return "bg-slate-800 text-slate-200";
  if (confidence > 0.7) return "bg-emerald-500/15 text-emerald-200";
  if (confidence >= 0.4) return "bg-amber-500/15 text-amber-200";
  return "bg-rose-500/15 text-rose-200";
}

function isNearBottom(element: HTMLDivElement): boolean {
  const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
  return remaining <= SCROLL_BOTTOM_THRESHOLD;
}

function formatTime(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function TypingIndicator() {
  return (
    <article className="flex justify-start">
      <div className="max-w-[90%] rounded-2xl border border-slate-800/90 bg-slate-900/75 px-4 py-3">
        <p className="text-xs uppercase tracking-wide text-slate-400">Assistant</p>
        <div className="mt-2 inline-flex items-center gap-1.5 text-sm text-slate-300">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:240ms]" />
          <span className="ml-1">Generating answer</span>
        </div>
      </div>
    </article>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-4 py-2">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className={clsx("flex", index % 2 === 0 ? "justify-start" : "justify-end")}>
          <div className="w-[72%] animate-pulse rounded-2xl border border-slate-800/80 bg-slate-900/70 px-4 py-3">
            <div className="mb-2 h-3 w-20 rounded bg-slate-800" />
            <div className="space-y-2">
              <div className="h-3 w-full rounded bg-slate-800" />
              <div className="h-3 w-[92%] rounded bg-slate-800" />
              <div className="h-3 w-[74%] rounded bg-slate-800" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChatInterface({
  projectId,
  sessionId,
  messages,
  setMessages,
  onSourcesSelect,
  disabled = false,
  isHistoryLoading = false,
}: ChatInterfaceProps) {
  const { sendMessage } = useChat();
  const draftKey = `chat-draft:${projectId}:${sessionId ?? "no-session"}`;

  const [question, setQuestion] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(draftKey) ?? "";
  });
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [useHyde, setUseHyde] = useState(true);
  const [showRetrievalOptions, setShowRetrievalOptions] = useState(false);
  const [expandedSourceMessageId, setExpandedSourceMessageId] = useState<string | null>(null);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const listRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (question) {
      window.localStorage.setItem(draftKey, question);
      return;
    }
    window.localStorage.removeItem(draftKey);
  }, [draftKey, question]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [question]);

  useEffect(() => {
    const container = listRef.current;
    if (!container) return;

    if (isNearBottom(container)) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
      setShowJumpToLatest(false);
      return;
    }

    setShowJumpToLatest(true);
  }, [messages, isSending]);

  const canSend = useMemo(
    () => Boolean(sessionId) && !disabled && !isSending && question.trim().length > 0,
    [disabled, isSending, question, sessionId],
  );

  const submitQuestion = async () => {
    if (!sessionId || !question.trim() || disabled || isSending) return;

    const prompt = question.trim();
    setQuestion("");
    setError(null);
    setIsSending(true);

    const optimisticUser: WorkspaceMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: prompt,
      createdAt: new Date().toISOString(),
      confidence: null,
      sources: [],
      confidenceBreakdown: null,
    };

    setMessages((prev) => [...prev, optimisticUser]);

    try {
      const result = await sendMessage(projectId, sessionId, prompt, {
        retrieval_mode: retrievalMode,
        use_hyde: useHyde,
      });

      const assistantMessage: WorkspaceMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: result.answer,
        createdAt: new Date().toISOString(),
        confidence: result.confidence,
        sources: result.sources,
        confidenceBreakdown: result.confidence_breakdown,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Failed to send message");
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitQuestion();
  };

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-slate-950/35 shadow-[inset_0_1px_0_rgba(148,163,184,0.06)]">
      <div
        ref={listRef}
        onScroll={() => {
          const container = listRef.current;
          if (!container) return;
          setShowJumpToLatest(!isNearBottom(container));
        }}
        className="min-h-0 flex-1 space-y-7 overflow-y-auto overscroll-contain px-5 py-6 transition-opacity duration-200 md:px-6"
        role="log"
        aria-live="polite"
        aria-busy={isHistoryLoading || isSending}
      >
        {!isHistoryLoading && messages.length === 0 ? (
          <div className="mx-auto max-w-2xl rounded-2xl border border-dashed border-slate-700/80 bg-slate-900/30 px-6 py-8 text-center transition-opacity duration-200">
            <h3 className="text-base font-medium text-slate-200">
              {sessionId ? "Start your research conversation" : "Choose a session to begin"}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              {sessionId
                ? "This chat helps you reason over project documents with citations you can inspect in the evidence panel."
                : "Sessions preserve context so your questions, answers, and evidence trails stay organized over long research work."}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {sessionId
                ? "Ask a focused question to get a grounded answer, confidence signal, and linked sources."
                : "Create a new session in the left sidebar, then ask your first document-grounded question."}
            </p>
          </div>
        ) : null}

        {isHistoryLoading ? (
          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 px-4 py-4 transition-opacity duration-200">
            <p className="text-xs uppercase tracking-wide text-slate-500">Loading session timeline</p>
            <p className="mt-1 text-xs text-slate-400">
              Restoring previous questions, answers, and citation context.
            </p>
            <HistorySkeleton />
          </div>
        ) : null}

        {!isHistoryLoading
          ? messages.map((message) => {
              const isAssistant = message.role === "assistant";
              const sourceCount = message.sources.length;
              const expanded = expandedSourceMessageId === message.id;

              return (
                <article key={message.id} className={clsx("flex", isAssistant ? "justify-start" : "justify-end")}>
                  <div
                    className={clsx(
                      "space-y-2.5",
                      isAssistant ? "max-w-[90%] sm:max-w-[84%]" : "max-w-[86%] sm:max-w-[78%]",
                    )}
                  >
                    <div className="flex items-center gap-2 px-1">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500">
                        {isAssistant ? "Assistant" : "You"}
                      </p>
                      <p className="text-[11px] text-slate-500">{formatTime(message.createdAt)}</p>
                    </div>

                    <div
                      className={clsx(
                        "rounded-2xl px-4 py-3.5 shadow-sm transition-colors",
                        isAssistant
                          ? "border border-slate-800/90 bg-slate-900/75 text-slate-100"
                          : "bg-slate-200 text-slate-900",
                      )}
                    >
                      {isAssistant ? (
                        <MarkdownRenderer
                          content={message.content}
                          onCitationClick={(indices) => {
                            if (!indices.length) return;
                            const prioritized = indices
                              .map((index) => message.sources[index])
                              .filter((source): source is SourceChunkResponse => Boolean(source));
                            const remaining = message.sources.filter(
                              (source) => !prioritized.some((picked) => picked.chunk_id === source.chunk_id),
                            );
                            const orderedSources = [...prioritized, ...remaining];
                            if (orderedSources.length > 0) {
                              onSourcesSelect(orderedSources);
                              setExpandedSourceMessageId(message.id);
                            }
                          }}
                        />
                      ) : (
                        <p className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
                      )}
                    </div>

                    {isAssistant ? (
                      <div className="space-y-2 px-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={clsx(
                              "inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium",
                              confidenceClass(message.confidence),
                            )}
                          >
                            Confidence {normalizeConfidence(message.confidence)}
                          </span>

                          {sourceCount > 0 ? (
                            <button
                              type="button"
                              onClick={() => {
                                if (expanded) {
                                  setExpandedSourceMessageId(null);
                                  onSourcesSelect([]);
                                  return;
                                }
                                setExpandedSourceMessageId(message.id);
                                onSourcesSelect(message.sources);
                              }}
                              className="rounded-full border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 transition-colors hover:border-cyan-400/70 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                            >
                              {expanded ? "Hide sources" : `Inspect sources (${sourceCount})`}
                            </button>
                          ) : null}
                        </div>

                        {sourceCount > 0 ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {message.sources.slice(0, 4).map((source, index) => (
                              <button
                                key={source.chunk_id}
                                type="button"
                                onClick={() => {
                                  const remaining = message.sources.filter((item) => item.chunk_id !== source.chunk_id);
                                  onSourcesSelect([source, ...remaining]);
                                  setExpandedSourceMessageId(message.id);
                                }}
                                className="max-w-[220px] truncate rounded-md border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                                title={source.source_filename}
                              >
                                [{index + 1}] {source.source_filename}
                              </button>
                            ))}
                            {sourceCount > 4 ? (
                              <span className="text-[11px] text-slate-400">+{sourceCount - 4} more</span>
                            ) : null}
                          </div>
                        ) : null}

                        {message.confidenceBreakdown ? <ConfidenceBar breakdown={message.confidenceBreakdown} /> : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })
          : null}

        {isSending ? <TypingIndicator /> : null}
      </div>

      {showJumpToLatest ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-28 flex justify-center">
          <button
            type="button"
            onClick={() => {
              const container = listRef.current;
              if (!container) return;
              container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
              setShowJumpToLatest(false);
            }}
            className="pointer-events-auto rounded-full border border-slate-700 bg-slate-900/95 px-3 py-1.5 text-xs text-slate-200 shadow-lg transition-colors duration-150 hover:border-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            Jump to latest
          </button>
        </div>
      ) : null}

      <form
        onSubmit={handleSubmit}
        className="border-t border-slate-800/90 bg-slate-950/75 px-4 pb-4 pt-3 backdrop-blur supports-[backdrop-filter]:bg-slate-950/70 md:px-5"
      >
        <div className="mb-2 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setShowRetrievalOptions((prev) => !prev)}
            className="text-xs text-slate-400 transition-colors hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            {showRetrievalOptions ? "Hide retrieval options" : "Show retrieval options"}
          </button>
          <p className="text-[11px] text-slate-500">Enter to send, Shift+Enter for newline</p>
        </div>

        {showRetrievalOptions ? (
          <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-slate-800/90 bg-slate-900/65 px-3 py-2">
            <label className="text-xs text-slate-300">
              Retrieval mode
              <select
                value={retrievalMode}
                onChange={(event) => setRetrievalMode(event.target.value as RetrievalMode)}
                className="ml-2 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 outline-none focus:border-slate-500 focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              >
                <option value="hybrid">hybrid</option>
                <option value="dense">dense</option>
                <option value="sparse">sparse</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={useHyde}
                onChange={(event) => setUseHyde(event.target.checked)}
                className="rounded border-slate-600 bg-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              />
              HyDE enabled
            </label>
          </div>
        ) : null}

        <div className="rounded-2xl border border-slate-800/90 bg-slate-900/75 p-2">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (canSend) {
                    void submitQuestion();
                  }
                }
              }}
              rows={1}
              placeholder={
                disabled
                  ? "Upload documents to unlock chat."
                  : sessionId
                    ? "Ask a question about your documents..."
                    : "Select a session to start chatting..."
              }
              className="max-h-[220px] min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              disabled={disabled || !sessionId}
            />
            <button
              type="submit"
              disabled={!canSend}
              className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSending ? "Sending..." : "Send"}
            </button>
          </div>
        </div>

        {error ? (
          <p className="mt-2 text-xs text-rose-300" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </section>
  );
}
