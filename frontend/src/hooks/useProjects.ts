"use client";

import useSWR from "swr";

import { authFetch } from "@/lib/auth";
import {
  ProjectCreateResponse,
  ProjectListResponse,
  ProjectResponse,
} from "@/lib/types";

const PROJECTS_KEY = "/projects";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;

  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.message ?? "Request failed");
  }

  return payload as T;
}

async function fetchProjects(): Promise<ProjectListResponse> {
  const response = await authFetch(PROJECTS_KEY, { method: "GET" });
  return parseJsonOrThrow<ProjectListResponse>(response);
}

export function useProjects() {
  const { data, error, isLoading, mutate } = useSWR<ProjectListResponse>(PROJECTS_KEY, fetchProjects, {
    revalidateOnFocus: true,
  });

  const createProject = async (name: string, description?: string): Promise<ProjectCreateResponse> => {
    const response = await authFetch(PROJECTS_KEY, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, description }),
    });

    const created = await parseJsonOrThrow<ProjectCreateResponse>(response);
    await mutate();
    return created;
  };

  const deleteProject = async (id: string): Promise<void> => {
    const response = await authFetch(`/projects/${id}`, {
      method: "DELETE",
    });

    await parseJsonOrThrow<{ message: string }>(response);
    await mutate();
  };

  const renameProject = async (id: string, name: string): Promise<ProjectResponse> => {
    const response = await authFetch(`/projects/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name }),
    });

    const updated = await parseJsonOrThrow<ProjectResponse>(response);
    await mutate();
    return updated;
  };

  return {
    projects: data?.projects ?? [],
    error,
    isLoading,
    mutateProjects: mutate,
    createProject,
    deleteProject,
    renameProject,
  };
}
