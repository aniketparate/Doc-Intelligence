"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { authFetch, clearAccessToken } from "@/lib/auth";
import { UserResponse } from "@/lib/types";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;

  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.message ?? "Request failed");
  }

  return payload as T;
}

export function useAuth() {
  const router = useRouter();

  const getCurrentUser = useCallback(async (): Promise<UserResponse> => {
    const response = await authFetch("/auth/me", { method: "GET" });
    return parseJsonOrThrow<UserResponse>(response);
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    try {
      const response = await authFetch("/auth/logout", { method: "POST" });
      await parseJsonOrThrow<{ message: string }>(response);
    } finally {
      clearAccessToken();
      router.replace("/login");
    }
  }, [router]);

  return {
    getCurrentUser,
    logout,
  };
}
