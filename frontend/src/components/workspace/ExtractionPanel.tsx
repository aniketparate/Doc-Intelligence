"use client";

import { useState } from "react";

import { authFetch } from "@/lib/auth";
import { ExtractResponse } from "@/lib/types";

type ExtractionPanelProps = {
  projectId: string;
  sessionId: string | null;
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

export function ExtractionPanel({ projectId, sessionId }: ExtractionPanelProps) {
  const [prompt, setPrompt] = useState("Extract key entities and values as structured JSON.");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasRunOnce, setHasRunOnce] = useState(false);

  const runExtraction = async () => {
    if (!sessionId || isLoading) return;

    setIsLoading(true);
    setError(null);
    setHasRunOnce(true);

    try {
      const response = await authFetch(`/projects/${projectId}/extract`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          prompt,
          top_k: 5,
          retrieval_mode: "hybrid",
          use_hyde: true,
        }),
      });

      const result = await parseJsonOrThrow<ExtractResponse>(response);
      setData(result.data);
    } catch (extractError) {
      setError(extractError instanceof Error ? extractError.message : "Extraction failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-800/90 bg-slate-900/60 p-4 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)]">
      <h3 className="text-sm font-semibold tracking-tight text-slate-100">Extraction</h3>
      <p className="mt-1 text-xs text-slate-400">Generate structured JSON from project context.</p>

      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        rows={3}
        className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs leading-relaxed text-slate-100 outline-none transition-colors duration-150 focus:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/70"
      />

      <button
        type="button"
        onClick={() => {
          void runExtraction();
        }}
        disabled={!sessionId || isLoading}
        className="mt-3 rounded-lg bg-cyan-400 px-3 py-2 text-xs font-semibold text-slate-950 transition-colors duration-150 hover:bg-cyan-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? "Running..." : "Run Extraction"}
      </button>

      {!sessionId ? (
        <div className="mt-3 rounded-lg border border-dashed border-slate-700/80 px-3 py-3 transition-opacity duration-200">
          <p className="text-sm text-slate-300">Select a session to run extraction.</p>
          <p className="mt-1 text-xs text-slate-500">
            Extraction uses the active research conversation to produce structured outputs with project grounding.
          </p>
          <p className="mt-1 text-xs text-slate-500">Choose a session, ask a question, then run extraction for JSON output.</p>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}

      {sessionId && !isLoading && !data && !error ? (
        <div className="mt-3 rounded-lg border border-dashed border-slate-700/80 px-3 py-3 transition-opacity duration-200">
          <p className="text-sm text-slate-300">
            {hasRunOnce ? "No structured output returned yet." : "Ready to extract structured output."}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Use extraction to convert retrieved evidence into fields your team can review, compare, and reuse.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Refine the prompt above and run extraction to populate a field-by-field result table.
          </p>
        </div>
      ) : null}

      {isLoading ? (
        <div className="mt-4 overflow-hidden rounded-lg border border-slate-800 transition-opacity duration-200">
          <div className="border-b border-slate-800 bg-slate-950/60 px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Building structured result</p>
            <p className="mt-1 text-[11px] text-slate-400">
              Retrieving context, validating evidence, and formatting fields.
            </p>
          </div>
          <div className="space-y-2 px-3 py-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="grid grid-cols-[140px_minmax(0,1fr)] gap-2">
                <div className="h-3 animate-pulse rounded bg-slate-800" />
                <div className="h-3 animate-pulse rounded bg-slate-800" />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data && !isLoading ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-800 transition-opacity duration-200">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-slate-950/80">
                <th className="border-b border-slate-800 px-3 py-2 text-left font-medium text-slate-300">Field</th>
                <th className="border-b border-slate-800 px-3 py-2 text-left font-medium text-slate-300">Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data).map(([key, value]) => (
                <tr key={key} className="align-top">
                  <td className="border-b border-slate-800 px-3 py-2 font-medium text-slate-200">{key}</td>
                  <td className="border-b border-slate-800 px-3 py-2 text-slate-300">
                    {typeof value === "object" ? (
                      <pre className="whitespace-pre-wrap text-xs text-slate-300">{JSON.stringify(value, null, 2)}</pre>
                    ) : (
                      String(value)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
