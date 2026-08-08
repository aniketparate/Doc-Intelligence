"use client";

import { Fragment, ReactNode, useMemo, useState } from "react";

type MarkdownRendererProps = {
  content: string;
  onCitationClick?: (indices: number[]) => void;
};

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "unordered-list"; items: string[] }
  | { type: "ordered-list"; items: string[] }
  | { type: "blockquote"; text: string }
  | { type: "code"; language: string; code: string };

const CITATION_PATTERN = /^\[(\d+(?:\s*,\s*\d+)*)\]$/;

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    const fenceMatch = trimmed.match(/^```([a-zA-Z0-9_-]+)?$/);
    if (fenceMatch) {
      const language = fenceMatch[1]?.trim() ?? "";
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i]?.trim().startsWith("```") ?? false)) {
        codeLines.push(lines[i] ?? "");
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({
        type: "code",
        language,
        code: codeLines.join("\n").trimEnd(),
      });
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length as 1 | 2 | 3;
      blocks.push({ type: "heading", level, text: headingMatch[2] });
      i += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length) {
        const candidate = lines[i]?.trim() ?? "";
        if (!candidate.startsWith(">")) break;
        quoteLines.push(candidate.replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "blockquote", text: quoteLines.join(" ") });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const candidate = (lines[i] ?? "").trim();
        const match = candidate.match(/^[-*]\s+(.+)$/);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push({ type: "unordered-list", items });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const candidate = (lines[i] ?? "").trim();
        const match = candidate.match(/^\d+\.\s+(.+)$/);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push({ type: "ordered-list", items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (i < lines.length) {
      const candidate = lines[i] ?? "";
      const candidateTrimmed = candidate.trim();
      if (!candidateTrimmed) break;
      if (
        /^```/.test(candidateTrimmed) ||
        /^(#{1,3})\s+/.test(candidateTrimmed) ||
        /^[-*]\s+/.test(candidateTrimmed) ||
        /^\d+\.\s+/.test(candidateTrimmed) ||
        candidateTrimmed.startsWith(">")
      ) {
        break;
      }
      paragraphLines.push(candidateTrimmed);
      i += 1;
    }

    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function parseInline(text: string, onCitationClick?: (indices: number[]) => void): ReactNode[] {
  const pieces: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|\[(\d+(?:\s*,\s*\d+)*)\])/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      pieces.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("`") && token.endsWith("`")) {
      pieces.push(
        <code key={`${match.index}-code`} className="rounded bg-slate-800/70 px-1.5 py-0.5 font-mono text-[0.88em] text-slate-100">
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**") && token.endsWith("**")) {
      pieces.push(
        <strong key={`${match.index}-strong`} className="font-semibold text-slate-100">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("[") && token.includes("](") && token.endsWith(")")) {
      const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (linkMatch) {
        pieces.push(
          <a
            key={`${match.index}-link`}
            href={linkMatch[2]}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-slate-500 underline-offset-2 transition-colors hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            {linkMatch[1]}
          </a>,
        );
      } else {
        pieces.push(token);
      }
    } else if (CITATION_PATTERN.test(token)) {
      const citationMatch = token.match(CITATION_PATTERN);
      const indices = citationMatch?.[1]
        .split(",")
        .map((item) => Number.parseInt(item.trim(), 10) - 1)
        .filter((value) => Number.isInteger(value) && value >= 0);

      pieces.push(
        <button
          key={`${match.index}-citation`}
          type="button"
          aria-label={`Inspect citation ${token}`}
          title={`Inspect citation ${token}`}
          onClick={() => {
            if (!indices || indices.length === 0) return;
            onCitationClick?.(indices);
          }}
          className="rounded-md border border-slate-700/90 bg-slate-800/80 px-1.5 py-0.5 font-mono text-[0.8em] text-slate-100 transition-colors hover:border-slate-500 hover:bg-slate-700/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
        >
          {token}
        </button>,
      );
    } else {
      pieces.push(token);
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    pieces.push(text.slice(lastIndex));
  }

  return pieces;
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800/90 bg-slate-950/80">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <span className="text-[11px] uppercase tracking-wide text-slate-400">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(code);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1200);
            } catch {
              setCopied(false);
            }
          }}
          className="rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="max-h-[340px] overflow-x-auto overscroll-contain p-3 text-[13px] leading-relaxed text-slate-100">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

export function MarkdownRenderer({ content, onCitationClick }: MarkdownRendererProps) {
  const blocks = useMemo(() => parseBlocks(content), [content]);

  return (
    <div className="space-y-3 break-words text-[15px] leading-7 text-slate-200">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;

        if (block.type === "heading") {
          if (block.level === 1) {
            return (
              <h2 key={key} className="text-lg font-semibold text-slate-100">
                {parseInline(block.text, onCitationClick)}
              </h2>
            );
          }

          if (block.level === 2) {
            return (
              <h3 key={key} className="text-base font-semibold text-slate-100">
                {parseInline(block.text, onCitationClick)}
              </h3>
            );
          }

          return (
            <h4 key={key} className="text-sm font-semibold uppercase tracking-wide text-slate-200">
              {parseInline(block.text, onCitationClick)}
            </h4>
          );
        }

        if (block.type === "paragraph") {
          return (
            <p key={key} className="whitespace-pre-wrap leading-7">
              {parseInline(block.text, onCitationClick).map((node, nodeIndex) => (
                <Fragment key={`${key}-inline-${nodeIndex}`}>{node}</Fragment>
              ))}
            </p>
          );
        }

        if (block.type === "unordered-list") {
          return (
            <ul key={key} className="list-disc space-y-1.5 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {parseInline(item, onCitationClick).map((node, nodeIndex) => (
                    <Fragment key={`${key}-${itemIndex}-${nodeIndex}`}>{node}</Fragment>
                  ))}
                </li>
              ))}
            </ul>
          );
        }

        if (block.type === "ordered-list") {
          return (
            <ol key={key} className="list-decimal space-y-1.5 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {parseInline(item, onCitationClick).map((node, nodeIndex) => (
                    <Fragment key={`${key}-${itemIndex}-${nodeIndex}`}>{node}</Fragment>
                  ))}
                </li>
              ))}
            </ol>
          );
        }

        if (block.type === "blockquote") {
          return (
            <blockquote key={key} className="rounded-r-md border-l-2 border-slate-600 bg-slate-900/45 py-1 pl-3 pr-2 text-slate-300">
              {parseInline(block.text, onCitationClick).map((node, nodeIndex) => (
                <Fragment key={`${key}-quote-${nodeIndex}`}>{node}</Fragment>
              ))}
            </blockquote>
          );
        }

        return <CodeBlock key={key} code={block.code} language={block.language} />;
      })}
    </div>
  );
}
