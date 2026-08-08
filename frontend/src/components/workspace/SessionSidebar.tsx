"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { MessageSquarePlus, Search, Trash2, X } from "lucide-react";

import { authFetch } from "@/lib/auth";
import { ChatSessionListResponse, ChatSessionResponse } from "@/lib/types";

type SessionSidebarProps = {
  projectId: string;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string | null) => void;
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

async function fetchSessions(path: string): Promise<ChatSessionListResponse> {
  const response = await authFetch(path, { method: "GET" });
  return parseJsonOrThrow<ChatSessionListResponse>(response);
}

function formatTimeAgo(isoDate: string): string {
  const ts = new Date(isoDate).getTime();
  if (Number.isNaN(ts)) return "Unknown";

  const diff = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  const units: Array<{ max: number; unit: Intl.RelativeTimeFormatUnit; seconds: number }> = [
    { max: 60, unit: "second", seconds: 1 },
    { max: 3600, unit: "minute", seconds: 60 },
    { max: 86400, unit: "hour", seconds: 3600 },
    { max: 604800, unit: "day", seconds: 86400 },
    { max: 2629800, unit: "week", seconds: 604800 },
    { max: 31557600, unit: "month", seconds: 2629800 },
    { max: Number.POSITIVE_INFINITY, unit: "year", seconds: 31557600 },
  ];

  const selected = units.find((item) => diff < item.max) ?? units[units.length - 1];
  const value = -Math.floor(diff / selected.seconds);
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(value, selected.unit);
}

export function SessionSidebar({ projectId, activeSessionId, onSelectSession }: SessionSidebarProps) {
  const key = useMemo(() => `/projects/${projectId}/sessions`, [projectId]);
  const { data, error, isLoading, mutate } = useSWR<ChatSessionListResponse>(key, fetchSessions, {
    revalidateOnFocus: true,
  });

  const [isCreating, setIsCreating] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const sessions = useMemo(() => data?.sessions ?? [], [data?.sessions]);
  const filteredSessions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return sessions;
    return sessions.filter((session) =>
      (session.title?.trim() || "Untitled chat").toLowerCase().includes(normalizedQuery),
    );
  }, [query, sessions]);

  const handleNewChat = async () => {
    if (isCreating) return;
    setIsCreating(true);

    try {
      const response = await authFetch(`/projects/${projectId}/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      const created = await parseJsonOrThrow<ChatSessionResponse>(response);
      await mutate();
      onSelectSession(created.id);
    } catch {
      // Surface fetch errors through next revalidation cycle; keep UI responsive.
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (sessionId: string) => {
    setPendingDeleteId(sessionId);
    try {
      const response = await authFetch(`/projects/${projectId}/sessions/${sessionId}`, {
        method: "DELETE",
      });
      await parseJsonOrThrow<{ message: string }>(response);
      await mutate();
      if (activeSessionId === sessionId) {
        onSelectSession(null);
      }
    } finally {
      setPendingDeleteId(null);
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-slate-900/60 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)]">
      <div className="space-y-3 border-b border-slate-800/90 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-slate-100">Sessions</h3>
            <p className="text-xs text-slate-500">
              {sessions.length} total{query.trim() ? ` | ${filteredSessions.length} shown` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              void handleNewChat();
            }}
            disabled={isCreating}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/70 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition-colors duration-150 hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            {isCreating ? "Creating..." : "New"}
          </button>
        </div>

        <label className="relative block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search sessions"
            aria-label="Search sessions"
            className="w-full rounded-lg border border-slate-800 bg-slate-950/75 py-2 pl-8 pr-8 text-sm text-slate-100 outline-none transition-colors duration-150 placeholder:text-slate-400 focus:border-slate-600 focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition-colors hover:text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              aria-label="Clear search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3" aria-busy={isLoading}>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="animate-pulse rounded-xl border border-slate-800/80 bg-slate-950/50 px-3 py-3"
              >
                <div className="mb-2 h-3 w-2/3 rounded bg-slate-800" />
                <div className="h-2.5 w-1/3 rounded bg-slate-800" />
              </div>
            ))}
          </div>
        ) : null}
        {error ? <p className="px-2 text-xs text-rose-300">{error.message}</p> : null}

        {!isLoading && !error && sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700/80 px-3 py-4 transition-opacity duration-200">
            <p className="text-sm text-slate-300">No sessions yet.</p>
            <p className="mt-1 text-xs text-slate-500">
              Sessions preserve long research threads so you can return to context without losing progress.
            </p>
            <p className="mt-1 text-xs text-slate-500">Start a new session to begin asking document-grounded questions.</p>
          </div>
        ) : null}

        {!isLoading && !error && sessions.length > 0 && filteredSessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700/80 px-3 py-4 transition-opacity duration-200">
            <p className="text-sm text-slate-300">No matching sessions.</p>
            <p className="mt-1 text-xs text-slate-500">
              Search helps you jump back into prior reasoning, citations, and decisions.
            </p>
            <button
              type="button"
              onClick={() => setQuery("")}
              className="mt-2 text-xs text-slate-400 transition-colors hover:text-slate-200"
            >
              Clear search
            </button>
          </div>
        ) : null}

        <ul className="space-y-2">
          {filteredSessions.map((session) => {
            const isActive = session.id === activeSessionId;
            const deleting = pendingDeleteId === session.id;
            return (
              <li key={session.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  aria-current={isActive ? "true" : undefined}
                  className={`w-full rounded-xl border px-3 py-2.5 pr-10 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 ${
                    isActive
                      ? "border-slate-600 bg-slate-800/85"
                      : "border-transparent bg-slate-950/40 hover:bg-slate-900/70"
                  }`}
                >
                  <p className="line-clamp-1 text-sm font-medium text-slate-100">
                    {session.title?.trim() || "Untitled chat"}
                  </p>
                  <div className="mt-1 flex items-center gap-2">
                    <p className="text-xs text-slate-500">{formatTimeAgo(session.updated_at)}</p>
                    {isActive ? (
                      <span className="rounded-full bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-200">
                        Active
                      </span>
                    ) : null}
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void handleDelete(session.id);
                  }}
                  className={`absolute right-2 top-2 rounded-md p-1 text-slate-500 transition hover:text-rose-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300/70 ${
                    isActive
                      ? "opacity-100"
                      : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                  }`}
                  aria-label="Delete session"
                >
                  {deleting ? <span className="text-xs">...</span> : <Trash2 className="h-3.5 w-3.5" />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
