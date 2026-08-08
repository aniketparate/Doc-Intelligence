"use client";

import useSWR from "swr";

import { authFetch } from "@/lib/auth";
import {
  DocumentListResponse,
  DocumentResponse,
  DocumentUploadResponse,
} from "@/lib/types";

function isProcessing(status: DocumentResponse["status"]): boolean {
  return status === "pending" || status === "processing";
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

async function fetchDocuments(path: string): Promise<DocumentListResponse> {
  const response = await authFetch(path, { method: "GET" });
  return parseJsonOrThrow<DocumentListResponse>(response);
}

export function useDocuments(projectId: string | null) {
  const key = projectId ? `/projects/${projectId}/documents` : null;

  const { data, error, isLoading, mutate } = useSWR<DocumentListResponse>(key, fetchDocuments, {
    refreshInterval: (latestData) => {
      const docs = latestData?.documents ?? [];
      return docs.some((doc) => isProcessing(doc.status)) ? 3000 : 0;
    },
    revalidateOnFocus: true,
  });

  const uploadDocuments = async (targetProjectId: string, files: File[]): Promise<DocumentUploadResponse> => {
    if (files.length === 0) {
      return { documents: [] };
    }

    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    const response = await authFetch(`/projects/${targetProjectId}/documents`, {
      method: "POST",
      body: formData,
    });

    const uploaded = await parseJsonOrThrow<DocumentUploadResponse>(response);
    await mutate();
    return uploaded;
  };

  return {
    documents: data?.documents ?? [],
    error,
    isLoading,
    mutateDocuments: mutate,
    uploadDocuments,
  };
}
