"use client";

import { ConfidenceBreakdown } from "@/lib/types";

type ConfidenceBarProps = {
  breakdown: ConfidenceBreakdown;
};

const SEGMENTS: Array<{
  key: keyof ConfidenceBreakdown;
  label: string;
  color: string;
}> = [
  { key: "retrieval_score", label: "Retrieval", color: "bg-cyan-400" },
  { key: "chunk_agreement", label: "Agreement", color: "bg-emerald-400" },
  { key: "answer_coverage", label: "Coverage", color: "bg-amber-400" },
  { key: "source_count", label: "Sources", color: "bg-fuchsia-400" },
];

function clamp(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function ConfidenceBar({ breakdown }: ConfidenceBarProps) {
  const values = SEGMENTS.map((segment) => ({
    ...segment,
    value: clamp(breakdown[segment.key]),
  }));

  const sum = values.reduce((acc, current) => acc + current.value, 0);

  return (
    <div className="space-y-2">
      <div className="flex h-2 overflow-hidden rounded bg-slate-800">
        {values.map((segment) => {
          const width = sum > 0 ? (segment.value / sum) * 100 : 0;
          return (
            <span
              key={segment.key}
              className={segment.color}
              style={{ width: `${width}%` }}
              title={`${segment.label}: ${segment.value.toFixed(2)}`}
            />
          );
        })}
      </div>

      <div className="flex flex-wrap gap-2 text-[11px] text-slate-400">
        {values.map((segment) => (
          <span key={segment.key} className="inline-flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${segment.color}`} />
            {segment.label} {segment.value.toFixed(2)}
          </span>
        ))}
      </div>
    </div>
  );
}
