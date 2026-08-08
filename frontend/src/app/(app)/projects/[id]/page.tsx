"use client";

import { CSSProperties, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { BookOpenText, Files, MessageSquareText, Sparkles } from "lucide-react";

import { ChatInterface, WorkspaceMessage } from "@/components/chat/ChatInterface";
import { DocumentList } from "@/components/workspace/DocumentList";
import { ExtractionPanel } from "@/components/workspace/ExtractionPanel";
import { SessionSidebar } from "@/components/workspace/SessionSidebar";
import { SourcePanel } from "@/components/source-panel/SourcePanel";
import { UploadPanel } from "@/components/workspace/UploadPanel";
import { useChat } from "@/hooks/useChat";
import { authFetch, ensureAccessToken } from "@/lib/auth";
import { ChatMessageResponse, ProjectResponse, SourceChunkResponse } from "@/lib/types";

const LEFT_PANE_MIN = 280;
const LEFT_PANE_MAX = 460;
const RIGHT_PANE_MIN = 320;
const RIGHT_PANE_MAX = 520;
const DEFAULT_LEFT_PANE = 330;
const DEFAULT_RIGHT_PANE = 370;

type MobilePane = "sessions" | "documents" | "chat" | "evidence";
type ResizeHandle = "left" | "right" | null;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStoredPaneWidth(
  projectId: string | null,
  side: "leftPaneWidth" | "rightPaneWidth",
  fallback: number,
  min: number,
  max: number,
): number {
  if (typeof window === "undefined" || !projectId) return fallback;
  const key = `workspace-layout:${projectId}`;
  const raw = window.localStorage.getItem(key);
  if (!raw) return fallback;

  try {
    const parsed = JSON.parse(raw) as { leftPaneWidth?: number; rightPaneWidth?: number };
    const value = parsed[side];
    if (typeof value === "number") {
      return clamp(value, min, max);
    }
  } catch {
    // Ignore malformed persisted layout values.
  }

  return fallback;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;

  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.message ?? "Request failed");
  }

  return payload as T;
}

function normalizeSources(input: unknown): SourceChunkResponse[] {
  if (!Array.isArray(input)) return [];

  const result: SourceChunkResponse[] = [];
  for (const item of input) {
    if (typeof item !== "object" || item === null) continue;

    const record = item as {
      chunk_id?: unknown;
      text?: unknown;
      page?: unknown;
      source_filename?: unknown;
      reranker_score?: unknown;
    };

    if (typeof record.chunk_id !== "string" || typeof record.text !== "string") continue;

    result.push({
      chunk_id: record.chunk_id,
      text: record.text,
      page: typeof record.page === "number" ? record.page : null,
      source_filename:
        typeof record.source_filename === "string" ? record.source_filename : "Unknown source",
      reranker_score: typeof record.reranker_score === "number" ? record.reranker_score : null,
    });
  }

  return result;
}

function mapHistoryMessage(message: ChatMessageResponse): WorkspaceMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    confidence: message.confidence,
    sources: normalizeSources(message.sources),
    confidenceBreakdown: null,
  };
}

export default function ProjectWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { loadHistory } = useChat();

  const projectId = useMemo(() => {
    const value = params?.id;
    if (Array.isArray(value)) return value[0] ?? null;
    return value ?? null;
  }, [params]);

  const [authChecked, setAuthChecked] = useState(false);
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [hasDocuments, setHasDocuments] = useState(false);
  const [selectedSources, setSelectedSources] = useState<SourceChunkResponse[]>([]);
  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false);
  const [mobilePane, setMobilePane] = useState<MobilePane>("chat");
  const [leftPaneWidth, setLeftPaneWidth] = useState(() =>
    readStoredPaneWidth(projectId, "leftPaneWidth", DEFAULT_LEFT_PANE, LEFT_PANE_MIN, LEFT_PANE_MAX),
  );
  const [rightPaneWidth, setRightPaneWidth] = useState(() =>
    readStoredPaneWidth(projectId, "rightPaneWidth", DEFAULT_RIGHT_PANE, RIGHT_PANE_MIN, RIGHT_PANE_MAX),
  );
  const [activeResizeHandle, setActiveResizeHandle] = useState<ResizeHandle>(null);
  const [isDesktopLayout, setIsDesktopLayout] = useState(false);

  useEffect(() => {
    let active = true;

    const checkAuthAndProject = async () => {
      if (!projectId) {
        setProjectError("Missing project id");
        return;
      }

      const token = await ensureAccessToken();
      if (!active) return;

      if (!token) {
        router.replace("/login");
        return;
      }

      setAuthChecked(true);

      try {
        const response = await authFetch(`/projects/${projectId}`, {
          method: "GET",
        });
        const currentProject = await parseJsonOrThrow<ProjectResponse>(response);
        if (!active) return;
        setProject(currentProject);
      } catch (projectLoadError) {
        if (!active) return;
        setProjectError(
          projectLoadError instanceof Error ? projectLoadError.message : "Failed to load project",
        );
      }
    };

    void checkAuthAndProject();

    return () => {
      active = false;
    };
  }, [projectId, router]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateDesktopMode = () => {
      setIsDesktopLayout(window.innerWidth >= 1280);
    };

    updateDesktopMode();
    window.addEventListener("resize", updateDesktopMode);
    return () => window.removeEventListener("resize", updateDesktopMode);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !projectId) return;
    const key = `workspace-layout:${projectId}`;
    window.localStorage.setItem(
      key,
      JSON.stringify({
        leftPaneWidth,
        rightPaneWidth,
      }),
    );
  }, [leftPaneWidth, projectId, rightPaneWidth]);

  useEffect(() => {
    if (!activeResizeHandle || !isDesktopLayout) return;

    const onMouseMove = (event: MouseEvent) => {
      const viewportWidth = window.innerWidth;

      if (activeResizeHandle === "left") {
        const next = clamp(event.clientX - 16, LEFT_PANE_MIN, LEFT_PANE_MAX);
        setLeftPaneWidth(next);
        return;
      }

      const next = clamp(viewportWidth - event.clientX - 16, RIGHT_PANE_MIN, RIGHT_PANE_MAX);
      setRightPaneWidth(next);
    };

    const onMouseUp = () => setActiveResizeHandle(null);

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [activeResizeHandle, isDesktopLayout]);

  const adjustPaneWidth = useCallback((handle: "left" | "right", delta: number) => {
    if (handle === "left") {
      setLeftPaneWidth((current) => clamp(current + delta, LEFT_PANE_MIN, LEFT_PANE_MAX));
      return;
    }
    setRightPaneWidth((current) => clamp(current + delta, RIGHT_PANE_MIN, RIGHT_PANE_MAX));
  }, []);

  const handleSelectSession = useCallback(
    async (sessionId: string | null) => {
      if (!projectId) return;

      setActiveSessionId(sessionId);
      setSelectedSources([]);
      setHistoryError(null);

      if (!sessionId) {
        setMessages([]);
        return;
      }

      setHistoryLoading(true);
      try {
        const history = await loadHistory(projectId, sessionId);
        setMessages(history.messages.map(mapHistoryMessage));
        setMobilePane("chat");
      } catch (loadError) {
        setHistoryError(loadError instanceof Error ? loadError.message : "Failed to load session history");
        setMessages([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [loadHistory, projectId],
  );

  if (!projectId) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <section className="w-full max-w-md rounded-2xl border border-rose-500/30 bg-rose-500/10 px-5 py-4">
          <p className="text-sm font-medium text-rose-200">Project ID is missing from the route.</p>
          <p className="mt-1 text-xs text-rose-200/80">
            Open a project from the dashboard to restore its sessions, documents, and evidence workspace.
          </p>
        </section>
      </main>
    );
  }

  if (!authChecked) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <section className="w-full max-w-lg rounded-2xl border border-slate-800/90 bg-slate-900/55 p-5">
          <p className="text-xs uppercase tracking-wide text-slate-500">Preparing workspace</p>
          <div className="mt-3 space-y-2.5">
            <div className="h-2 w-1/3 animate-pulse rounded bg-slate-800" />
            <div className="h-2 w-full animate-pulse rounded bg-slate-800" />
            <div className="h-2 w-4/5 animate-pulse rounded bg-slate-800" />
          </div>
          <p className="mt-4 text-sm text-slate-400">
            Verifying access and loading project context for chat, sources, and document indexing.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1700px] flex-col overflow-x-clip px-3 py-3 lg:px-5">
      <header className="mb-3 border-b border-slate-800/80 px-1 pb-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-[22px] font-semibold tracking-tight text-slate-100">{project?.name ?? "Project Workspace"}</h1>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">
              {project?.description?.trim() || "Ask questions across all documents in this project."}
            </p>
          </div>
          <p className="rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1 text-[11px] text-slate-400">
            Research workspace
          </p>
        </div>
        {projectError ? <p className="mt-2 text-xs text-rose-300">{projectError}</p> : null}
      </header>

      <div
        className="sticky top-0 z-20 -mx-1 mb-3 flex gap-2 overflow-x-auto bg-slate-950/80 px-1 pb-1 pt-1 backdrop-blur xl:hidden"
        aria-label="Workspace sections"
      >
        <button
          type="button"
          onClick={() => setMobilePane("sessions")}
          aria-pressed={mobilePane === "sessions"}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors duration-150 ${
            mobilePane === "sessions"
              ? "border-slate-700 bg-slate-800 text-slate-100"
              : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70`}
        >
          <MessageSquareText className="h-3.5 w-3.5" />
          Sessions
        </button>
        <button
          type="button"
          onClick={() => setMobilePane("documents")}
          aria-pressed={mobilePane === "documents"}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors duration-150 ${
            mobilePane === "documents"
              ? "border-slate-700 bg-slate-800 text-slate-100"
              : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70`}
        >
          <Files className="h-3.5 w-3.5" />
          Documents
        </button>
        <button
          type="button"
          onClick={() => setMobilePane("chat")}
          aria-pressed={mobilePane === "chat"}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors duration-150 ${
            mobilePane === "chat"
              ? "border-slate-700 bg-slate-800 text-slate-100"
              : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70`}
        >
          <BookOpenText className="h-3.5 w-3.5" />
          Chat
        </button>
        <button
          type="button"
          onClick={() => setMobilePane("evidence")}
          aria-pressed={mobilePane === "evidence"}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors duration-150 ${
            mobilePane === "evidence"
              ? "border-slate-700 bg-slate-800 text-slate-100"
              : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200"
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          Evidence
        </button>
      </div>

      <section className="min-h-0 flex-1">
        <div className="xl:hidden">
          <div
            className={`grid gap-3 ${
              mobilePane === "sessions" || mobilePane === "documents" ? "min-h-[72vh]" : "hidden"
            }`}
          >
            <div className={mobilePane === "sessions" ? "block" : "hidden"}>
              <SessionSidebar
                projectId={projectId}
                activeSessionId={activeSessionId}
                onSelectSession={(sessionId) => {
                  void handleSelectSession(sessionId);
                }}
              />
            </div>
            <div className={mobilePane === "documents" ? "block" : "hidden"}>
              <DocumentList
                projectId={projectId}
                onAddDocuments={() => setUploadDrawerOpen(true)}
                onDocumentsChange={(documents) => {
                  const hasAny = documents.length > 0;
                  setHasDocuments(hasAny);
                  if (!hasAny) {
                    setUploadDrawerOpen(false);
                  }
                }}
              />
            </div>
          </div>

          <section className={`${mobilePane === "chat" ? "relative flex min-h-[72vh] flex-col gap-3" : "hidden"}`}>
            {!hasDocuments ? (
              <UploadPanel
                projectId={projectId}
                hasDocuments={false}
                open
                onClose={() => {
                  // no-op in full-panel mode
                }}
                onUploaded={() => {
                  setHasDocuments(true);
                }}
              />
            ) : null}

            {historyError ? <p className="text-sm text-rose-300" role="alert">{historyError}</p> : null}

            <div className="min-h-0 flex-1">
              <ChatInterface
                key={activeSessionId ?? "no-session"}
                projectId={projectId}
                sessionId={activeSessionId}
                messages={messages}
                setMessages={setMessages}
                onSourcesSelect={setSelectedSources}
                disabled={!hasDocuments}
                isHistoryLoading={historyLoading}
              />
            </div>

            {hasDocuments ? (
              <UploadPanel
                projectId={projectId}
                hasDocuments
                open={uploadDrawerOpen}
                onClose={() => setUploadDrawerOpen(false)}
                onUploaded={() => {
                  setUploadDrawerOpen(false);
                }}
              />
            ) : null}
          </section>

          <aside className={mobilePane === "evidence" ? "space-y-3" : "hidden"}>
            <SourcePanel
              key={selectedSources.map((source) => source.chunk_id).join("|")}
              sources={selectedSources}
            />
            <ExtractionPanel projectId={projectId} sessionId={activeSessionId} />
          </aside>
        </div>

        <div
          className="hidden min-h-0 flex-1 xl:grid xl:gap-0"
          style={
            {
              gridTemplateColumns: `${leftPaneWidth}px 10px minmax(0,1fr) 10px ${rightPaneWidth}px`,
            } as CSSProperties
          }
        >
          <aside className="min-h-0 pr-3">
            <div className="grid h-full min-h-0 gap-3 grid-rows-[minmax(250px,0.95fr)_minmax(300px,1.05fr)]">
              <SessionSidebar
                projectId={projectId}
                activeSessionId={activeSessionId}
                onSelectSession={(sessionId) => {
                  void handleSelectSession(sessionId);
                }}
              />
              <DocumentList
                projectId={projectId}
                onAddDocuments={() => setUploadDrawerOpen(true)}
                onDocumentsChange={(documents) => {
                  const hasAny = documents.length > 0;
                  setHasDocuments(hasAny);
                  if (!hasAny) {
                    setUploadDrawerOpen(false);
                  }
                }}
              />
            </div>
          </aside>

          <div className="group relative flex items-stretch justify-center">
            <div className="w-px bg-slate-800/80 transition-colors group-hover:bg-slate-600/80" />
            <button
              type="button"
              onMouseDown={() => setActiveResizeHandle("left")}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  adjustPaneWidth("left", -12);
                } else if (event.key === "ArrowRight") {
                  event.preventDefault();
                  adjustPaneWidth("left", 12);
                }
              }}
              className="absolute inset-y-0 left-1/2 w-3 -translate-x-1/2 cursor-col-resize rounded touch-none focus-visible:bg-slate-700/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              role="separator"
              tabIndex={0}
              aria-orientation="vertical"
              aria-label="Resize left panel"
              aria-valuemin={LEFT_PANE_MIN}
              aria-valuemax={LEFT_PANE_MAX}
              aria-valuenow={leftPaneWidth}
            />
          </div>

          <section className="relative flex min-h-0 flex-col px-3">
            {!hasDocuments ? (
              <UploadPanel
                projectId={projectId}
                hasDocuments={false}
                open
                onClose={() => {
                  // no-op in full-panel mode
                }}
                onUploaded={() => {
                  setHasDocuments(true);
                }}
              />
            ) : null}

            {historyError ? <p className="mb-2 text-sm text-rose-300" role="alert">{historyError}</p> : null}

            <div className="min-h-0 flex-1">
              <ChatInterface
                key={activeSessionId ?? "no-session"}
                projectId={projectId}
                sessionId={activeSessionId}
                messages={messages}
                setMessages={setMessages}
                onSourcesSelect={setSelectedSources}
                disabled={!hasDocuments}
                isHistoryLoading={historyLoading}
              />
            </div>

            {hasDocuments ? (
              <UploadPanel
                projectId={projectId}
                hasDocuments
                open={uploadDrawerOpen}
                onClose={() => setUploadDrawerOpen(false)}
                onUploaded={() => {
                  setUploadDrawerOpen(false);
                }}
              />
            ) : null}
          </section>

          <div className="group relative flex items-stretch justify-center">
            <div className="w-px bg-slate-800/80 transition-colors group-hover:bg-slate-600/80" />
            <button
              type="button"
              onMouseDown={() => setActiveResizeHandle("right")}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  adjustPaneWidth("right", 12);
                } else if (event.key === "ArrowRight") {
                  event.preventDefault();
                  adjustPaneWidth("right", -12);
                }
              }}
              className="absolute inset-y-0 left-1/2 w-3 -translate-x-1/2 cursor-col-resize rounded touch-none focus-visible:bg-slate-700/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              role="separator"
              tabIndex={0}
              aria-orientation="vertical"
              aria-label="Resize right panel"
              aria-valuemin={RIGHT_PANE_MIN}
              aria-valuemax={RIGHT_PANE_MAX}
              aria-valuenow={rightPaneWidth}
            />
          </div>

          <aside className="min-h-0 space-y-3 pl-3">
            <SourcePanel
              key={selectedSources.map((source) => source.chunk_id).join("|")}
              sources={selectedSources}
            />
            <ExtractionPanel projectId={projectId} sessionId={activeSessionId} />
          </aside>
        </div>
      </section>
    </main>
  );
}
