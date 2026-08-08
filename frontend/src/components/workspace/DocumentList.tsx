"use client";

import { useEffect, useMemo } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Timer } from "lucide-react";

import { useDocuments } from "@/hooks/useDocuments";
import { DocumentResponse } from "@/lib/types";

type DocumentListProps = {
  projectId: string;
  onAddDocuments: () => void;
  onDocumentsChange?: (documents: DocumentResponse[]) => void;
};

const STATUS_CLASS: Record<DocumentResponse["status"], string> = {
  pending: "bg-slate-500/20 text-slate-200 border-slate-500/30",
  processing: "bg-amber-500/20 text-amber-200 border-amber-500/30",
  ready: "bg-emerald-500/20 text-emerald-200 border-emerald-500/30",
  failed: "bg-rose-500/20 text-rose-200 border-rose-500/30",
};

const STATUS_DETAIL: Record<
  DocumentResponse["status"],
  {
    label: string;
    ingestionState: string;
    indexingState: string;
    progress: number;
    helper: string;
  }
> = {
  pending: {
    label: "Pending ingestion",
    ingestionState: "Stored",
    indexingState: "Queued",
    progress: 38,
    helper: "File uploaded. Ingestion is queued.",
  },
  processing: {
    label: "Indexing",
    ingestionState: "Parsed",
    indexingState: "Generating chunks",
    progress: 78,
    helper: "Chunking and indexing are in progress.",
  },
  ready: {
    label: "Ready",
    ingestionState: "Complete",
    indexingState: "Indexed",
    progress: 100,
    helper: "Document is searchable in chat.",
  },
  failed: {
    label: "Failed",
    ingestionState: "Failed",
    indexingState: "Stopped",
    progress: 100,
    helper: "Indexing failed. See error details.",
  },
};

const STATUS_PRIORITY: Record<DocumentResponse["status"], number> = {
  processing: 0,
  pending: 1,
  failed: 2,
  ready: 3,
};

export function DocumentList({ projectId, onAddDocuments, onDocumentsChange }: DocumentListProps) {
  const { documents, error, isLoading } = useDocuments(projectId);

  useEffect(() => {
    onDocumentsChange?.(documents);
  }, [documents, onDocumentsChange]);

  const orderedDocuments = useMemo(() => {
    return [...documents].sort((a, b) => {
      const statusCompare = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
      if (statusCompare !== 0) return statusCompare;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [documents]);

  const summary = useMemo(() => {
    const total = documents.length;
    const pending = documents.filter((doc) => doc.status === "pending").length;
    const processing = documents.filter((doc) => doc.status === "processing").length;
    const ready = documents.filter((doc) => doc.status === "ready").length;
    const failed = documents.filter((doc) => doc.status === "failed").length;
    return { total, pending, processing, ready, failed };
  }, [documents]);

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-slate-900/60 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)]">
      <div className="border-b border-slate-800 px-4 py-3">
        <h3 className="text-sm font-semibold tracking-tight text-slate-100">Documents</h3>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-slate-300">{summary.total} total</span>
          <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-slate-300">
            {summary.pending + summary.processing} indexing
          </span>
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-200">{summary.ready} ready</span>
          {summary.failed > 0 ? (
            <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-200">{summary.failed} failed</span>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3" aria-busy={isLoading}>
        {isLoading ? (
          <div className="space-y-2.5 transition-opacity duration-200">
            <p className="px-1 text-[11px] uppercase tracking-wide text-slate-500">Loading document index</p>
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="animate-pulse rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-3">
                <div className="mb-2 h-3.5 w-2/3 rounded bg-slate-800" />
                <div className="mb-2 h-2 w-full rounded bg-slate-800" />
                <div className="grid grid-cols-3 gap-2">
                  <div className="h-8 rounded bg-slate-800" />
                  <div className="h-8 rounded bg-slate-800" />
                  <div className="h-8 rounded bg-slate-800" />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 transition-opacity duration-200">
            <p className="text-xs text-rose-200">{error.message}</p>
          </div>
        ) : null}

        {!isLoading && documents.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700/80 px-3 py-4 transition-opacity duration-200">
            <p className="text-sm text-slate-300">No documents are indexed yet.</p>
            <p className="mt-1 text-xs text-slate-500">
              Indexed documents make chat answers grounded, citable, and easier to verify during research.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Use Add More Documents below to upload files and track ingestion, indexing, and chunk counts.
            </p>
          </div>
        ) : null}

        <ul className="space-y-2.5 transition-opacity duration-200">
          {orderedDocuments.map((document) => {
            const detail = STATUS_DETAIL[document.status];
            const isRunning = document.status === "pending" || document.status === "processing";
            return (
              <li key={document.id} className="rounded-xl border border-slate-800/90 bg-slate-950/55 px-3 py-3 transition-colors duration-150 hover:border-slate-700">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-100" title={document.filename}>
                      {document.filename}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">{detail.helper}</p>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${STATUS_CLASS[document.status]}`}
                  >
                    {isRunning ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                    {detail.label}
                  </span>
                </div>

                <div className="h-1.5 overflow-hidden rounded bg-slate-800">
                  <div
                    className={`h-full transition-[width] duration-300 ${
                      document.status === "ready"
                        ? "bg-emerald-400"
                        : document.status === "failed"
                          ? "bg-rose-500"
                          : document.status === "processing"
                            ? "bg-amber-400"
                            : "bg-slate-400"
                    } ${isRunning ? "animate-pulse" : ""}`}
                    style={{ width: `${detail.progress}%` }}
                  />
                </div>

                <div className="mt-2 grid grid-cols-1 gap-2 text-[11px] text-slate-300 sm:grid-cols-3">
                  <div className="rounded-md bg-slate-900/80 px-2 py-1">
                    <p className="text-slate-500">Ingestion</p>
                    <p className="mt-0.5 text-slate-200">{detail.ingestionState}</p>
                  </div>
                  <div className="rounded-md bg-slate-900/80 px-2 py-1">
                    <p className="text-slate-500">Indexing</p>
                    <p className="mt-0.5 text-slate-200">{detail.indexingState}</p>
                  </div>
                  <div className="rounded-md bg-slate-900/80 px-2 py-1">
                    <p className="text-slate-500">Chunks</p>
                    <p className="mt-0.5 text-slate-200">
                      {document.num_chunks !== null
                        ? document.num_chunks
                        : document.status === "ready"
                          ? "0"
                          : "Calculating..."}
                    </p>
                  </div>
                </div>

                {document.status === "processing" ? (
                  <p className="mt-2 inline-flex items-center gap-1 text-[11px] text-amber-200">
                    <Timer className="h-3 w-3" />
                    Indexing underway.
                  </p>
                ) : null}

                {document.status === "ready" ? (
                  <p className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-200">
                    <CheckCircle2 className="h-3 w-3" />
                    Ready for retrieval and citations.
                  </p>
                ) : null}

                {document.status === "failed" ? (
                  <div className="mt-2 rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5">
                    <p className="inline-flex items-start gap-1 text-[11px] text-rose-200">
                      <AlertTriangle className="mt-[1px] h-3 w-3 shrink-0" />
                      {document.error_message || "Indexing failed. Re-upload or inspect the file format."}
                    </p>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="border-t border-slate-800 p-3">
        <button
          type="button"
          onClick={onAddDocuments}
          className="w-full rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm font-medium text-cyan-200 transition-colors hover:border-cyan-300 hover:bg-cyan-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
        >
          + Add More Documents
        </button>
      </div>
    </section>
  );
}
