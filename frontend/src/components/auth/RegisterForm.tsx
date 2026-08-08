"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import zxcvbn from "zxcvbn";

import { apiRequest } from "@/lib/api";
import { AuthRegisterRequest, MessageResponse } from "@/lib/types";

import { SsoButtons } from "./SsoButtons";

const strengthLabels = ["Very weak", "Weak", "Fair", "Strong", "Very strong"];
const strengthColors = [
  "bg-rose-500",
  "bg-orange-500",
  "bg-amber-500",
  "bg-lime-500",
  "bg-emerald-500",
];

export function RegisterForm() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const strength = useMemo(() => zxcvbn(password).score, [password]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: AuthRegisterRequest = {
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
      };

      await apiRequest<MessageResponse, AuthRegisterRequest>("/auth/register", {
        method: "POST",
        body: payload,
      });

      router.push(
        `/verify-otp?purpose=verify_email&email=${encodeURIComponent(payload.email)}`,
      );
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Registration failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div className="space-y-2">
        <label className="text-sm text-slate-200" htmlFor="full_name">
          Full name
        </label>
        <input
          required
          id="full_name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
          placeholder="Jane Doe"
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm text-slate-200" htmlFor="email">
          Email
        </label>
        <input
          required
          id="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
          placeholder="you@example.com"
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm text-slate-200" htmlFor="password">
          Password
        </label>
        <input
          required
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
          placeholder="At least 8 chars and one number"
        />
        <div className="space-y-1">
          <div className="h-2 w-full overflow-hidden rounded bg-slate-800">
            <div
              className={`h-full transition-all ${strengthColors[strength]}`}
              style={{ width: `${((strength + 1) / 5) * 100}%` }}
            />
          </div>
          <p className="text-xs text-slate-400">
            Password strength:{" "}
            <span className="font-medium text-slate-200">{strengthLabels[strength]}</span>
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm text-slate-200" htmlFor="confirm_password">
          Confirm password
        </label>
        <input
          required
          id="confirm_password"
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
          placeholder="Re-enter your password"
        />
      </div>

      {error ? <p className="text-sm text-rose-300">{error}</p> : null}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-lg bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting ? "Creating account..." : "Create account"}
      </button>

      <div className="relative py-2">
        <div className="absolute inset-x-0 top-1/2 border-t border-slate-700" />
        <span className="relative mx-auto block w-fit bg-slate-900 px-2 text-xs uppercase tracking-wide text-slate-400">
          Or
        </span>
      </div>

      <SsoButtons />
    </form>
  );
}
