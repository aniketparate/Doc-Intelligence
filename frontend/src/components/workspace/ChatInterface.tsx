"use client";

import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useRef, useState } from "react";

import { ConfidenceBar } from "@/components/workspace/ConfidenceBar";
import { useChat } from "@/hooks/useChat";
import { ConfidenceBreakdown, RetrievalMode, SourceChunkResponse } from "@/lib/types";

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
};

function normalizeConfidence(confidence: number | null): string {
  if (confidence === null || Number.isNaN(confidence)) return "N/A";
  return `${Math.round(confidence * 100)}%`;
}

function confidenceClass(confidence: number | null): string {
  if (confidence === null || Number.isNaN(confidence)) return "bg-slate-700 text-slate-200";
  if (confidence > 0.7) return "bg-emerald-500/20 text-emerald-200";
  if (confidence >= 0.4) return "bg-amber-500/20 text-amber-200";
  return "bg-rose-500/20 text-rose-200";
}

export function ChatInterface({
  projectId,
  sessionId,
  messages,
  setMessages,
  onSourcesSelect,
  disabled = false,
}: ChatInterfaceProps) {
  const { sendMessage } = useChat();
  const [question, setQuestion] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [useHyde, setUseHyde] = useState(true);
  const [expandedSourceMessageId, setExpandedSourceMessageId] = useState<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

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
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-900/60">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-center">
            <p className="text-sm text-slate-300">
              {sessionId
                ? "Ask anything about your project documents."
                : "Create or select a chat session to begin."}
            </p>
          </div>
        ) : null}

        {messages.map((message) => {
          const isAssistant = message.role === "assistant";
          const sourceCount = message.sources.length;
          const expanded = expandedSourceMessageId === message.id;

          return (
            <article
              key={message.id}
              className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                  isAssistant
                    ? "border border-slate-700 bg-slate-950/70 text-slate-100"
                    : "bg-cyan-400 text-slate-950"
                }`}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

                {isAssistant ? (
                  <div className="mt-3 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${confidenceClass(message.confidence)}`}
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
                          className="rounded-full border border-slate-600 px-2 py-0.5 text-[11px] text-slate-200 hover:border-cyan-300"
                        >
                          {sourceCount} sources
                        </button>
                      ) : null}
                    </div>

                    {message.confidenceBreakdown ? (
                      <ConfidenceBar breakdown={message.confidenceBreakdown} />
                    ) : null}
                  </div>
                ) : null}
              </div>
            </article>
          );
        })}

        <div ref={threadEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-800 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <label className="text-xs text-slate-300">
            Retrieval mode
            <select
              value={retrievalMode}
              onChange={(event) => setRetrievalMode(event.target.value as RetrievalMode)}
              className="ml-2 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
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
              className="rounded border-slate-600 bg-slate-950"
            />
            HyDE
          </label>
        </div>

        <div className="flex gap-2">
          <textarea
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
            rows={2}
            placeholder={disabled ? "Upload documents to unlock chat." : "Ask a question..."}
            className="min-h-[56px] flex-1 resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
            disabled={disabled || !sessionId}
          />
          <button
            type="submit"
            disabled={!canSend}
            className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSending ? "Sending..." : "Send"}
          </button>
        </div>

        {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}
      </form>
    </section>
  );
}
