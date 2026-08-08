"use client";

import { SourceChunkResponse } from "@/lib/types";

type SourcePanelProps = {
  sources: SourceChunkResponse[];
};

function scorePercent(score: number | null): number {
  if (score === null || Number.isNaN(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

export function SourcePanel({ sources }: SourcePanelProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <h3 className="text-sm font-semibold text-slate-100">Sources</h3>
      <p className="mt-1 text-xs text-slate-400">Retrieved chunks used by the selected answer.</p>

      {sources.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">Select an assistant answer to inspect sources.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {sources.map((source) => {
            const percent = scorePercent(source.reranker_score);
            return (
              <li key={source.chunk_id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="truncate text-xs font-medium text-slate-200" title={source.source_filename}>
                    {source.source_filename}
                  </p>
                  <span className="text-[11px] text-slate-400">Page {source.page ?? "-"}</span>
                </div>

                <div className="mb-2 h-1.5 overflow-hidden rounded bg-slate-800">
                  <div className="h-full bg-cyan-400" style={{ width: `${percent}%` }} />
                </div>
                <p className="mb-2 text-[11px] text-slate-400">Reranker score: {percent}%</p>

                <p className="max-h-40 overflow-y-auto text-xs leading-relaxed text-slate-300">{source.text}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
