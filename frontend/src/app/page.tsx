"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ensureAccessToken, getAccessToken } from "@/lib/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    let active = true;

    const resolveAuth = async () => {
      await ensureAccessToken();
      if (!active) return;

      if (getAccessToken()) {
        router.replace("/dashboard");
        return;
      }

      router.replace("/login");
    };

    void resolveAuth();

    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-md rounded-2xl border border-slate-800/90 bg-slate-900/55 p-5">
        <p className="text-xs uppercase tracking-wide text-slate-500">Preparing workspace</p>
        <div className="mt-3 space-y-2.5">
          <div className="h-2 w-2/5 animate-pulse rounded bg-slate-800" />
          <div className="h-2 w-full animate-pulse rounded bg-slate-800" />
          <div className="h-2 w-4/5 animate-pulse rounded bg-slate-800" />
        </div>
        <p className="mt-4 text-sm text-slate-400">
          Verifying your session so we can restore projects, chats, and document context.
        </p>
      </section>
    </main>
  );
}
