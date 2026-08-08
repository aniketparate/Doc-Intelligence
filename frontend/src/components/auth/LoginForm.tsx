"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { apiRequest } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import {
  AuthLoginRequest,
  AuthRequestOtpRequest,
  AuthTokenUserResponse,
  MessageResponse,
} from "@/lib/types";

import { SsoButtons } from "./SsoButtons";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpMode, setOtpMode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const normalizedEmail = email.trim().toLowerCase();

    try {
      if (otpMode) {
        const otpPayload: AuthRequestOtpRequest = { email: normalizedEmail };
        await apiRequest<MessageResponse, AuthRequestOtpRequest>("/auth/request-otp", {
          method: "POST",
          body: otpPayload,
        });
        router.push(`/verify-otp?purpose=login&email=${encodeURIComponent(normalizedEmail)}`);
        return;
      }

      const passwordPayload: AuthLoginRequest = {
        email: normalizedEmail,
        password,
      };
      const loginResult = await apiRequest<AuthTokenUserResponse, AuthLoginRequest>("/auth/login", {
        method: "POST",
        body: passwordPayload,
      });
      setAccessToken(loginResult.access_token);
      router.replace("/dashboard");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
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

      {!otpMode ? (
        <div className="space-y-2">
          <label className="text-sm text-slate-200" htmlFor="password">
            Password
          </label>
          <input
            required={!otpMode}
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
            placeholder="Your password"
          />
        </div>
      ) : null}

      <button
        type="button"
        className="text-sm font-medium text-cyan-300 hover:text-cyan-200"
        onClick={() => {
          setOtpMode((prev) => !prev);
          setError(null);
        }}
      >
        {otpMode ? "Use password instead" : "Sign in with OTP instead"}
      </button>

      {error ? <p className="text-sm text-rose-300">{error}</p> : null}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-lg bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting
          ? otpMode
            ? "Sending OTP..."
            : "Signing in..."
          : otpMode
            ? "Send OTP"
            : "Sign in"}
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
