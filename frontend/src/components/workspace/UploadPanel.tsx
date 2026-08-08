"use client";

import { useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw, Timer } from "lucide-react";

import { useDocuments } from "@/hooks/useDocuments";
import { authFetch } from "@/lib/auth";
import { DocumentResponse, DocumentStatus } from "@/lib/types";

type UploadPanelProps = {
  projectId: string;
  hasDocuments: boolean;
  open: boolean;
  onClose: () => void;
  onUploaded?: () => void;
};

type UploadStatus = "queued" | "uploading" | "pending" | "processing" | "ready" | "failed";

type UploadItem = {
  id: string;
  filename: string;
  status: UploadStatus;
  progress: number;
  docId?: string;
  error?: string;
  file?: File;
  numChunks?: number | null;
};

const ACCEPTED_FORMATS = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/msword": [".doc"],
  "text/plain": [".txt", ".md"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "text/html": [".html"],
  "application/epub+zip": [".epub"],
};

function mapDocStatus(status: DocumentStatus): { status: UploadStatus; progress: number } {
  switch (status) {
    case "pending":
      return { status: "pending", progress: 68 };
    case "processing":
      return { status: "processing", progress: 86 };
    case "ready":
      return { status: "ready", progress: 100 };
    case "failed":
      return { status: "failed", progress: 100 };
    default:
      return { status: "pending", progress: 70 };
  }
}

const STATUS_META: Record<
  UploadStatus,
  {
    label: string;
    ingestionState: string;
    indexingState: string;
    tone: string;
    progressTone: string;
  }
> = {
  queued: {
    label: "Queued",
    ingestionState: "Queued",
    indexingState: "Waiting",
    tone: "bg-slate-700/50 text-slate-200",
    progressTone: "bg-slate-500",
  },
  uploading: {
    label: "Uploading",
    ingestionState: "Uploading file",
    indexingState: "Not started",
    tone: "bg-cyan-500/15 text-cyan-200",
    progressTone: "bg-cyan-400",
  },
  pending: {
    label: "Ingestion pending",
    ingestionState: "Stored",
    indexingState: "Queued",
    tone: "bg-slate-700/50 text-slate-200",
    progressTone: "bg-slate-400",
  },
  processing: {
    label: "Indexing",
    ingestionState: "Parsed",
    indexingState: "Building chunks",
    tone: "bg-amber-500/15 text-amber-200",
    progressTone: "bg-amber-400",
  },
  ready: {
    label: "Indexed",
    ingestionState: "Complete",
    indexingState: "Indexed",
    tone: "bg-emerald-500/15 text-emerald-200",
    progressTone: "bg-emerald-400",
  },
  failed: {
    label: "Failed",
    ingestionState: "Failed",
    indexingState: "Stopped",
    tone: "bg-rose-500/15 text-rose-200",
    progressTone: "bg-rose-500",
  },
};

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;

  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.message ?? "Request failed");
  }

  return payload as T;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function UploadPanel({ projectId, hasDocuments, open, onClose, onUploaded }: UploadPanelProps) {
  const { uploadDocuments, mutateDocuments } = useDocuments(projectId);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    if (!hasDocuments) return;
    if (!open && !isUploading) {
      setItems([]);
      setError(null);
    }
  }, [hasDocuments, isUploading, open]);

  const pollStatus = async (
    docId: string,
    onUpdate: (document: DocumentResponse) => void,
  ): Promise<DocumentResponse> => {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const response = await authFetch(`/projects/${projectId}/documents/${docId}`, {
        method: "GET",
      });
      const document = await parseJsonOrThrow<DocumentResponse>(response);
      onUpdate(document);

      if (document.status === "ready" || document.status === "failed") {
        return document;
      }

      await sleep(3000);
    }

    throw new Error("Timed out while waiting for document processing");
  };

  const uploadFiles = async (files: File[]) => {
    if (files.length === 0 || isUploading) return;

    setError(null);
    setIsUploading(true);

    const initialItems = files.map((file, index) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${index}`,
      filename: file.name,
      status: "uploading" as UploadStatus,
      progress: 35,
      file,
      numChunks: null,
    }));
    setItems((prev) => [...prev, ...initialItems]);

    try {
      const uploadResult = await uploadDocuments(projectId, files);

      const queuedItems = initialItems.map((item, index) => {
        const doc = uploadResult.documents[index];
        if (!doc?.doc_id) {
          return {
            ...item,
            docId: undefined,
            status: "failed" as UploadStatus,
            progress: 100,
            error: "Upload response was missing a document id.",
          };
        }
        return {
          ...item,
          docId: doc.doc_id,
          status: "pending" as UploadStatus,
          progress: 68,
        };
      });
      setItems((prev) =>
        prev.map((entry) => queuedItems.find((queued) => queued.id === entry.id) ?? entry),
      );

      await Promise.all(
        queuedItems.map(async (item) => {
          if (!item.docId) return;

          try {
            const finalDoc = await pollStatus(item.docId, (currentDoc) => {
              const mapped = mapDocStatus(currentDoc.status);
              setItems((prev) =>
                prev.map((entry) =>
                  entry.id === item.id
                    ? {
                        ...entry,
                        status: mapped.status,
                        progress: mapped.progress,
                        numChunks: currentDoc.num_chunks ?? null,
                        error: currentDoc.error_message ?? undefined,
                      }
                    : entry,
                ),
              );
            });
            const finalMapped = mapDocStatus(finalDoc.status);
            setItems((prev) =>
              prev.map((entry) =>
                entry.id === item.id
                  ? {
                      ...entry,
                      status: finalMapped.status,
                      progress: finalMapped.progress,
                      numChunks: finalDoc.num_chunks ?? null,
                      error: finalDoc.error_message ?? undefined,
                    }
                  : entry,
              ),
            );
          } catch (pollError) {
            setItems((prev) =>
              prev.map((entry) =>
                entry.id === item.id
                  ? {
                      ...entry,
                      status: "failed",
                      progress: 100,
                      error: pollError instanceof Error ? pollError.message : "Polling failed",
                    }
                  : entry,
              ),
            );
          }
        }),
      );

      await mutateDocuments();
      onUploaded?.();

      const failedCount = queuedItems.filter((item) => item.status === "failed").length;
      if (hasDocuments && failedCount === 0) {
        onClose();
      }
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed");
      setItems((prev) =>
        prev.map((item) =>
          initialItems.some((initial) => initial.id === item.id)
            ? {
                ...item,
                status: "failed",
                progress: 100,
                error: uploadError instanceof Error ? uploadError.message : "Upload failed",
              }
            : item,
        ),
      );
    } finally {
      setIsUploading(false);
    }
  };

  const retryItem = async (itemId: string) => {
    if (isUploading) return;
    const target = items.find((item) => item.id === itemId);
    if (!target?.file) return;

    setItems((prev) =>
      prev.map((item) =>
        item.id === itemId
          ? {
              ...item,
              status: "queued",
              progress: 18,
              error: undefined,
              docId: undefined,
              numChunks: null,
            }
          : item,
      ),
    );
    await uploadFiles([target.file]);
    setItems((prev) => prev.filter((item) => item.id !== itemId));
  };

  const retryFailed = async () => {
    if (isUploading) return;
    const failedFiles = items
      .filter((item) => item.status === "failed" && item.file)
      .map((item) => item.file as File);
    if (failedFiles.length === 0) return;

    setItems((prev) =>
      prev.map((item) =>
        item.status === "failed"
          ? {
              ...item,
              status: "queued",
              progress: 18,
              error: undefined,
              docId: undefined,
              numChunks: null,
            }
          : item,
      ),
    );
    await uploadFiles(failedFiles);
    setItems((prev) => prev.filter((item) => item.status !== "queued"));
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED_FORMATS,
    multiple: true,
    onDrop: (acceptedFiles) => {
      void uploadFiles(acceptedFiles);
    },
    disabled: isUploading,
  });

  const statusLabel = useMemo(() => {
    if (isUploading) return "Uploading and indexing files...";
    return "Drop files here or click to browse";
  }, [isUploading]);

  const summary = useMemo(() => {
    const total = items.length;
    const ready = items.filter((item) => item.status === "ready").length;
    const failed = items.filter((item) => item.status === "failed").length;
    const inProgress = items.filter((item) => item.status !== "ready" && item.status !== "failed").length;
    return { total, ready, failed, inProgress };
  }, [items]);

  const panelBody = (
    <div className="space-y-4 transition-opacity duration-200">
      <div
        {...getRootProps({
          role: "button",
          "aria-label": "Upload documents",
        })}
        className={`cursor-pointer rounded-2xl border-2 border-dashed p-6 text-center transition-colors duration-150 focus-within:outline-none focus-within:ring-2 focus-within:ring-cyan-400/70 ${
          isDragActive
            ? "border-cyan-300 bg-cyan-500/10"
            : "border-slate-600 bg-slate-950/50 hover:border-cyan-400/70"
        }`}
      >
        <input {...getInputProps()} />
        <p className="text-sm font-medium text-slate-200">{statusLabel}</p>
        <p className="mt-2 text-xs text-slate-400">
          Supported: pdf, docx, doc, txt, md, xlsx, pptx, html, epub
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 transition-opacity duration-200">
          <p className="text-xs text-rose-200">{error}</p>
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
            <span className="rounded-full bg-slate-800/80 px-2 py-0.5">{summary.total} files</span>
            <span className="rounded-full bg-slate-800/80 px-2 py-0.5">{summary.inProgress} in progress</span>
            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-200">{summary.ready} ready</span>
            {summary.failed > 0 ? (
              <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-200">{summary.failed} failed</span>
            ) : null}
          </div>

          {summary.failed > 0 ? (
            <button
              type="button"
              onClick={() => {
                void retryFailed();
              }}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            >
              <RefreshCw className="h-3 w-3" />
              Retry failed files
            </button>
          ) : null}

          <ul className="space-y-2.5 transition-opacity duration-200">
            {items.map((item) => {
              const meta = STATUS_META[item.status];
              const isRunning = item.status === "pending" || item.status === "processing" || item.status === "uploading";
              return (
                <li key={item.id} className="rounded-xl border border-slate-800/90 bg-slate-950/60 px-3 py-3 transition-colors duration-150 hover:border-slate-700">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-100" title={item.filename}>
                        {item.filename}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-500">Progress {item.progress}%</p>
                    </div>

                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.tone}`}>
                      {isRunning ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                      {meta.label}
                    </span>
                  </div>

                  <div className="h-2 overflow-hidden rounded bg-slate-800">
                    <div
                      className={`h-full transition-[width] duration-300 ${meta.progressTone} ${isRunning ? "animate-pulse" : ""}`}
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>

                  <div className="mt-2 grid grid-cols-1 gap-2 text-[11px] text-slate-300 sm:grid-cols-3">
                    <div className="rounded-md bg-slate-900/80 px-2 py-1">
                      <p className="text-slate-500">Ingestion</p>
                      <p className="mt-0.5 text-slate-200">{meta.ingestionState}</p>
                    </div>
                    <div className="rounded-md bg-slate-900/80 px-2 py-1">
                      <p className="text-slate-500">Indexing</p>
                      <p className="mt-0.5 text-slate-200">{meta.indexingState}</p>
                    </div>
                    <div className="rounded-md bg-slate-900/80 px-2 py-1">
                      <p className="text-slate-500">Chunks</p>
                      <p className="mt-0.5 text-slate-200">
                        {item.numChunks !== undefined && item.numChunks !== null
                          ? item.numChunks
                          : item.status === "ready"
                            ? "0"
                            : "Calculating..."}
                      </p>
                    </div>
                  </div>

                  {item.status === "processing" ? (
                    <p className="mt-2 inline-flex items-center gap-1 text-[11px] text-amber-200">
                      <Timer className="h-3 w-3" />
                      Indexing in progress. This can take a little time for larger files.
                    </p>
                  ) : null}

                  {item.status === "ready" ? (
                    <p className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-200">
                      <CheckCircle2 className="h-3 w-3" />
                      File is indexed and ready for chat retrieval.
                    </p>
                  ) : null}

                  {item.error ? (
                    <div className="mt-2 rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5">
                      <p className="inline-flex items-start gap-1 text-[11px] text-rose-200">
                        <AlertCircle className="mt-[1px] h-3 w-3 shrink-0" />
                        {item.error}
                      </p>
                    </div>
                  ) : null}

                  {item.status === "failed" && item.file ? (
                    <button
                      type="button"
                      onClick={() => {
                        void retryItem(item.id);
                      }}
                      className="mt-2 inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                    >
                      <RefreshCw className="h-3 w-3" />
                      Retry file
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-700/80 px-4 py-5 transition-opacity duration-200">
          <p className="text-sm text-slate-300">Upload files to build project knowledge.</p>
          <p className="mt-1 text-xs text-slate-500">
            This panel tracks upload progress, ingestion state, indexing state, and chunk counts for each file.
          </p>
          <p className="mt-1 text-xs text-slate-500">Drop files above or click browse to start indexing for chat retrieval.</p>
        </div>
      )}
    </div>
  );

  if (!hasDocuments) {
    return (
      <section className="rounded-2xl border border-slate-800/90 bg-slate-900/60 p-6 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)]">
        <h2 className="text-lg font-semibold text-slate-100">Upload Documents to Start</h2>
        <p className="mt-1 text-sm text-slate-400">
          Add one or more files. Chat input unlocks after indexing completes.
        </p>
        <div className="mt-5">{panelBody}</div>
      </section>
    );
  }

  return (
    <aside
      className={`fixed inset-x-0 bottom-0 z-40 mx-auto max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-t-2xl border border-slate-700/90 bg-slate-900 p-4 shadow-2xl transition-transform duration-300 ${
        open ? "translate-y-0" : "translate-y-[93%]"
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Add More Documents</h3>
          <p className="text-xs text-slate-400">Track upload, ingestion, and indexing without leaving the workspace.</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
        >
          Close
        </button>
      </div>
      {panelBody}
    </aside>
  );
}
