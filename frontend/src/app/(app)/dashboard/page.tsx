"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { NewProjectModal } from "@/components/dashboard/NewProjectModal";
import { ProjectCard } from "@/components/dashboard/ProjectCard";
import { ensureAccessToken } from "@/lib/auth";
import { useProjects } from "@/hooks/useProjects";

export default function DashboardPage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { projects, isLoading, error, mutateProjects, deleteProject, renameProject } = useProjects();

  useEffect(() => {
    let active = true;

    const validateAuth = async () => {
      const token = await ensureAccessToken();
      if (!active) return;

      if (!token) {
        router.replace("/login");
        return;
      }

      setAuthChecked(true);
    };

    void validateAuth();

    return () => {
      active = false;
    };
  }, [router]);

  const handleRename = async (projectId: string, nextName: string) => {
    setActionError(null);
    try {
      await renameProject(projectId, nextName);
    } catch (renameError) {
      setActionError(renameError instanceof Error ? renameError.message : "Failed to rename project");
    }
  };

  const handleDelete = async (projectId: string) => {
    setActionError(null);
    try {
      await deleteProject(projectId);
    } catch (deleteError) {
      setActionError(deleteError instanceof Error ? deleteError.message : "Failed to delete project");
    }
  };

  if (!authChecked) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <section className="w-full max-w-lg rounded-2xl border border-slate-800/90 bg-slate-900/55 p-5">
          <p className="text-xs uppercase tracking-wide text-slate-500">Preparing dashboard</p>
          <div className="mt-3 space-y-2.5">
            <div className="h-2 w-1/3 animate-pulse rounded bg-slate-800" />
            <div className="h-2 w-full animate-pulse rounded bg-slate-800" />
            <div className="h-2 w-4/5 animate-pulse rounded bg-slate-800" />
          </div>
          <p className="mt-4 text-sm text-slate-400">
            Checking authentication and loading your workspace projects.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-7xl px-6 py-10">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-slate-100">Project Dashboard</h1>
          <p className="mt-2 text-sm text-slate-300">Manage isolated RAG workspaces and jump into analysis.</p>
        </div>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="rounded-lg bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
        >
          New Project
        </button>
      </header>

      {actionError ? <p className="mt-4 text-sm text-rose-300">{actionError}</p> : null}
      {error ? <p className="mt-4 text-sm text-rose-300">{error.message}</p> : null}

      {isLoading ? (
        <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <article
              key={index}
              className="animate-pulse rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5"
            >
              <div className="mb-4 h-4 w-2/3 rounded bg-slate-800" />
              <div className="mb-2 h-3 w-full rounded bg-slate-800" />
              <div className="mb-5 h-3 w-5/6 rounded bg-slate-800" />
              <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                <div className="h-8 rounded bg-slate-800" />
                <div className="h-8 rounded bg-slate-800" />
              </div>
            </article>
          ))}
        </section>
      ) : null}

      {!isLoading && projects.length === 0 ? (
        <section className="mt-10 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-12 text-center transition-opacity duration-200">
          <h2 className="text-xl font-medium text-slate-100">No projects yet</h2>
          <p className="mt-2 text-sm text-slate-400">
            Projects keep your research documents, sessions, and citations organized in one place.
          </p>
          <p className="mt-1 text-xs text-slate-500">Create a project to start uploading files and asking grounded questions.</p>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="mt-5 rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
          >
            Create First Project
          </button>
        </section>
      ) : null}

      {projects.length > 0 ? (
        <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onOpen={(projectId) => router.push(`/projects/${projectId}`)}
              onRename={handleRename}
              onDelete={handleDelete}
            />
          ))}
        </section>
      ) : null}

      {showModal ? (
        <NewProjectModal
          onClose={() => setShowModal(false)}
          onCreated={async () => {
            await mutateProjects();
          }}
        />
      ) : null}
    </main>
  );
}
