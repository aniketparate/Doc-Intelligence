"use client";

import { AskResponse, ChatMessageListResponse, ChatSessionResponse, RetrievalMode } from "@/lib/types";
import { authFetch } from "@/lib/auth";

type SendMessageOptions = {
  top_k?: number;
  retrieval_mode?: RetrievalMode;
  use_hyde?: boolean;
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

export function useChat() {
  const createSession = async (projectId: string): Promise<ChatSessionResponse> => {
    const response = await authFetch(`/projects/${projectId}/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    return parseJsonOrThrow<ChatSessionResponse>(response);
  };

  const sendMessage = async (
    projectId: string,
    sessionId: string,
    question: string,
    options: SendMessageOptions = {},
  ): Promise<AskResponse> => {
    const response = await authFetch(`/projects/${projectId}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        question,
        top_k: options.top_k ?? 5,
        retrieval_mode: options.retrieval_mode ?? "hybrid",
        use_hyde: options.use_hyde ?? true,
      }),
    });

    return parseJsonOrThrow<AskResponse>(response);
  };

  const loadHistory = async (projectId: string, sessionId: string): Promise<ChatMessageListResponse> => {
    const response = await authFetch(`/projects/${projectId}/sessions/${sessionId}/messages`, {
      method: "GET",
    });

    return parseJsonOrThrow<ChatMessageListResponse>(response);
  };

  return {
    createSession,
    sendMessage,
    loadHistory,
  };
}

export type { SendMessageOptions };
