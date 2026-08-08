"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Copy, FileText, Hash, Sparkles } from "lucide-react";

import { SourceChunkResponse } from "@/lib/types";

type SourcePanelProps = {
  sources: SourceChunkResponse[];
};

function scorePercent(score: number | null): number | null {
  if (score === null || Number.isNaN(score)) return null;
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

function scoreLabel(percent: number | null): string {
  if (percent === null) return "Unknown";
  if (percent >= 75) return "High relevance";
  if (percent >= 45) return "Medium relevance";
  return "Low relevance";
}

function scoreTone(percent: number | null): string {
  if (percent === null) return "bg-slate-800 text-slate-300";
  if (percent >= 75) return "bg-emerald-500/15 text-emerald-200";
  if (percent >= 45) return "bg-amber-500/15 text-amber-200";
  return "bg-rose-500/15 text-rose-200";
}

function splitChunkIntoParagraphs(text: string): string[] {
  return text
    .split(/\n{2,}/g)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function SourcePanel({ sources }: SourcePanelProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [showRetrievalDetails, setShowRetrievalDetails] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isSwitchingSource, setIsSwitchingSource] = useState(false);
  const switchTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (switchTimerRef.current !== null) {
        window.clearTimeout(switchTimerRef.current);
      }
    };
  }, []);

  const safeIndex = Math.min(activeIndex, Math.max(0, sources.length - 1));
  const activeSource = sources[safeIndex] ?? null;
  const isSwitching = isSwitchingSource && sources.length > 0;
  const percent = scorePercent(activeSource?.reranker_score ?? null);
  const paragraphs = useMemo(
    () => splitChunkIntoParagraphs(activeSource?.text ?? ""),
    [activeSource?.text],
  );

  const visibleParagraphs = expanded ? paragraphs : paragraphs.slice(0, 2);
  const hasHiddenParagraphs = paragraphs.length > visibleParagraphs.length;

  const selectSource = (nextIndex: number) => {
    if (nextIndex === safeIndex) return;
    if (switchTimerRef.current !== null) {
      window.clearTimeout(switchTimerRef.current);
    }
    setIsSwitchingSource(true);
    switchTimerRef.current = window.setTimeout(() => {
      setActiveIndex(nextIndex);
      setIsSwitchingSource(false);
      switchTimerRef.current = null;
    }, 140);
    setExpanded(false);
    setCopied(false);
    setShowRetrievalDetails(false);
  };

  const onCopyChunk = async () => {
    if (!activeSource?.text) return;
    try {
      await navigator.clipboard.writeText(activeSource.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-slate-900/60 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)]">
      <header className="border-b border-slate-800/90 px-4 py-3">
        <h3 className="text-sm font-semibold tracking-tight text-slate-100">Evidence</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">
          Inspect citations, chunk context, and retrieval confidence for the selected answer.
        </p>
      </header>

      {sources.length === 0 ? (
        <div className="px-4 py-6 transition-opacity duration-200">
          <p className="text-sm text-slate-300">Evidence inspection is available after an assistant response.</p>
          <p className="mt-1 text-xs text-slate-500">
            This panel lets you trace answers back to chunk-level citations, page metadata, and retrieval confidence.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Ask a question in chat, then click a citation or source chip to inspect supporting evidence.
          </p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="border-b border-slate-800/80 px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">
                Citation {safeIndex + 1} of {sources.length}
              </p>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => selectSource(Math.max(0, safeIndex - 1))}
                  disabled={safeIndex <= 0}
                  className="rounded-md border border-slate-700 p-1 text-slate-300 transition-colors duration-150 hover:border-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Previous citation"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => selectSource(Math.min(sources.length - 1, safeIndex + 1))}
                  disabled={safeIndex >= sources.length - 1}
                  className="rounded-md border border-slate-700 p-1 text-slate-300 transition-colors duration-150 hover:border-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Next citation"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  {sources.map((source, index) => (
                    <button
                      key={source.chunk_id}
                      type="button"
                      onClick={() => selectSource(index)}
                      title={source.source_filename}
                      className={`shrink-0 rounded-md border px-2.5 py-1 text-[11px] transition-colors duration-150 ${
                        index === safeIndex
                          ? "border-slate-500 bg-slate-800/90 text-slate-100"
                          : "border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-600 hover:text-slate-200"
                      } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70`}
                    >
                      <span className="font-mono">[{index + 1}]</span>{" "}
                      <span className="ml-1 inline-block max-w-[140px] truncate align-bottom">
                        {source.source_filename}
                      </span>
                    </button>
                  ))}
                </div>
          </div>

          {activeSource ? (
            <>
              <div className="space-y-3 border-b border-slate-800/80 px-4 py-3">
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                  <p className="line-clamp-2 text-sm font-medium text-slate-100" title={activeSource.source_filename}>
                    {activeSource.source_filename}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span className="inline-flex items-center gap-1 rounded-full bg-slate-800/90 px-2 py-0.5">
                    <Hash className="h-3 w-3" />
                    Page {activeSource.page ?? "-"}
                  </span>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${scoreTone(percent)}`}>
                    <Sparkles className="h-3 w-3" />
                    {scoreLabel(percent)}
                  </span>
                  <span className="rounded-full bg-slate-800/90 px-2 py-0.5 font-mono text-slate-300">
                    {activeSource.chunk_id.slice(0, 10)}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => setShowRetrievalDetails((current) => !current)}
                  aria-expanded={showRetrievalDetails}
                  className="inline-flex items-center gap-1 text-xs text-slate-400 transition-colors duration-150 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showRetrievalDetails ? "rotate-180" : ""}`} />
                  Retrieval details
                </button>

                {showRetrievalDetails ? (
                  <div className="space-y-2 rounded-lg border border-slate-800/70 bg-slate-950/45 px-3 py-2 text-xs text-slate-300">
                    <div className="flex items-center justify-between">
                      <span>Reranker score</span>
                      <span className="font-medium text-slate-100">{percent === null ? "N/A" : `${percent}%`}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded bg-slate-800">
                      <div
                        className={`h-full ${
                          percent === null
                            ? "bg-slate-600"
                            : percent >= 75
                              ? "bg-emerald-400"
                              : percent >= 45
                                ? "bg-amber-400"
                                : "bg-rose-400"
                        }`}
                        style={{ width: `${percent ?? 0}%` }}
                      />
                    </div>
                    <p className="text-[11px] text-slate-400">
                      This indicates how strongly this chunk matched the answer after reranking.
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3" aria-live="polite">
                {isSwitching ? (
                  <div className="space-y-3 py-1 transition-opacity duration-150">
                    <div className="h-3 w-24 animate-pulse rounded bg-slate-800" />
                    <div className="h-3 w-full animate-pulse rounded bg-slate-800" />
                    <div className="h-3 w-[94%] animate-pulse rounded bg-slate-800" />
                    <div className="h-3 w-[90%] animate-pulse rounded bg-slate-800" />
                  </div>
                ) : (
                  <div className="transition-opacity duration-200">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Chunk preview</p>
                      <button
                        type="button"
                        onClick={() => {
                          void onCopyChunk();
                        }}
                        className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors duration-150 hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                      >
                        <Copy className="h-3 w-3" />
                        {copied ? "Copied" : "Copy"}
                      </button>
                    </div>

                    <div className="space-y-3 text-sm leading-7 text-slate-200">
                      {visibleParagraphs.map((paragraph, index) => (
                        <p key={`${activeSource.chunk_id}-${index}`} className="whitespace-pre-wrap">
                          {paragraph}
                        </p>
                      ))}
                    </div>

                    {hasHiddenParagraphs ? (
                      <button
                        type="button"
                        onClick={() => setExpanded(true)}
                        aria-expanded={expanded}
                        className="mt-3 text-xs text-slate-400 transition-colors duration-150 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                      >
                        Show full chunk
                      </button>
                    ) : null}

                    {expanded && paragraphs.length > 2 ? (
                      <button
                        type="button"
                        onClick={() => setExpanded(false)}
                        className="mt-3 block text-xs text-slate-400 transition-colors duration-150 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                      >
                        Collapse chunk
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      )}
    </section>
  );
}
