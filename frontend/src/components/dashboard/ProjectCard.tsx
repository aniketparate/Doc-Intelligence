"use client";

import { useMemo, useState } from "react";
import { FolderKanban, Pencil, Trash2 } from "lucide-react";

import { ProjectResponse } from "@/lib/types";

type ProjectCardProps = {
  project: ProjectResponse;
  onOpen: (projectId: string) => void;
  onRename: (projectId: string, nextName: string) => Promise<void>;
  onDelete: (projectId: string) => Promise<void>;
};

function formatTimeAgo(isoDate: string): string {
  const target = new Date(isoDate).getTime();
  if (Number.isNaN(target)) return "Unknown";

  const diffSeconds = Math.max(1, Math.floor((Date.now() - target) / 1000));
  const ranges: Array<{ limit: number; unit: Intl.RelativeTimeFormatUnit; seconds: number }> = [
    { limit: 60, unit: "second", seconds: 1 },
    { limit: 3600, unit: "minute", seconds: 60 },
    { limit: 86400, unit: "hour", seconds: 3600 },
    { limit: 604800, unit: "day", seconds: 86400 },
    { limit: 2629800, unit: "week", seconds: 604800 },
    { limit: 31557600, unit: "month", seconds: 2629800 },
    { limit: Number.POSITIVE_INFINITY, unit: "year", seconds: 31557600 },
  ];

  const selected = ranges.find((entry) => diffSeconds < entry.limit) ?? ranges[ranges.length - 1];
  const value = -Math.floor(diffSeconds / selected.seconds);
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(value, selected.unit);
}

export function ProjectCard({ project, onOpen, onRename, onDelete }: ProjectCardProps) {
  const [isBusy, setIsBusy] = useState(false);
  const updatedLabel = useMemo(() => formatTimeAgo(project.updated_at), [project.updated_at]);

  const handleRename = async () => {
    const nextName = window.prompt("Rename project", project.name)?.trim();
    if (!nextName || nextName === project.name) return;

    setIsBusy(true);
    try {
      await onRename(project.id, nextName);
    } finally {
      setIsBusy(false);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm(`Delete \"${project.name}\"? This cannot be undone.`);
    if (!confirmed) return;

    setIsBusy(true);
    try {
      await onDelete(project.id);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(project.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(project.id);
        }
      }}
      className="group relative flex h-full cursor-pointer flex-col gap-4 rounded-2xl border border-slate-800/70 bg-slate-900/60 p-5 transition hover:border-cyan-400/60 hover:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-300">
            <FolderKanban className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-base font-semibold text-slate-100">{project.name}</h3>
            <p className="text-xs text-slate-400">Updated {updatedLabel}</p>
          </div>
        </div>

        <div className="flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
          <button
            type="button"
            disabled={isBusy}
            onClick={(event) => {
              event.stopPropagation();
              void handleRename();
            }}
            className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-cyan-400 hover:text-cyan-200 disabled:opacity-50"
            aria-label={`Rename ${project.name}`}
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            disabled={isBusy}
            onClick={(event) => {
              event.stopPropagation();
              void handleDelete();
            }}
            className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-rose-400 hover:text-rose-300 disabled:opacity-50"
            aria-label={`Delete ${project.name}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <p className="line-clamp-3 min-h-[3.75rem] text-sm text-slate-300">
        {project.description?.trim() || "No description provided yet."}
      </p>

      <dl className="mt-auto grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Documents</dt>
          <dd className="text-sm font-medium text-slate-100">{project.doc_count}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Chunks</dt>
          <dd className="text-sm font-medium text-slate-100">{project.chunk_count}</dd>
        </div>
      </dl>
    </article>
  );
}
