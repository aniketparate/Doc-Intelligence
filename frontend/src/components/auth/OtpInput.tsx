"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";

import { apiRequest } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { AuthTokenUserResponse, AuthVerifyOtpRequest, MessageResponse } from "@/lib/types";

type OtpPurpose = "verify_email" | "login";

type OtpInputProps = {
  email: string;
  purpose: OtpPurpose;
  onVerified: () => void;
};

const OTP_LENGTH = 6;
const RESEND_SECONDS = 60;

export function OtpInput({ email, purpose, onVerified }: OtpInputProps) {
  const [digits, setDigits] = useState<string[]>(Array(OTP_LENGTH).fill(""));
  const [countdown, setCountdown] = useState(RESEND_SECONDS);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  useEffect(() => {
    inputRefs.current[0]?.focus();
  }, []);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [countdown]);

  const verifyCode = async (code: string) => {
    if (submitting) return;
    setError(null);
    setSubmitting(true);

    try {
      const payload: AuthVerifyOtpRequest = {
        email,
        code,
        purpose,
      };
      const response = await apiRequest<AuthTokenUserResponse, AuthVerifyOtpRequest>("/auth/verify-otp", {
        method: "POST",
        body: payload,
      });
      setAccessToken(response.access_token);
      onVerified();
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : "Invalid verification code.");
      setDigits(Array(OTP_LENGTH).fill(""));
      inputRefs.current[0]?.focus();
    } finally {
      setSubmitting(false);
    }
  };

  const handleDigitInput = (index: number, value: string) => {
    if (!/^\d?$/.test(value)) return;
    setError(null);

    const updated = [...digits];
    updated[index] = value;
    setDigits(updated);

    if (value && index < OTP_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }

    const code = updated.join("");
    if (code.length === OTP_LENGTH && !updated.includes("")) {
      void verifyCode(code);
    }
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleResend = async () => {
    if (countdown > 0 || resending) return;
    setError(null);
    setResending(true);
    try {
      await apiRequest<MessageResponse, { email: string }>("/auth/request-otp", {
        method: "POST",
        body: { email },
      });
      setCountdown(RESEND_SECONDS);
    } catch (resendError) {
      if (purpose === "verify_email") {
        setError(
          "Resend is only available for login OTP in this flow. Re-submit registration if needed.",
        );
      } else {
        setError(resendError instanceof Error ? resendError.message : "Failed to resend code.");
      }
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        {digits.map((digit, index) => (
          <input
            key={index}
            ref={(element) => {
              inputRefs.current[index] = element;
            }}
            value={digit}
            maxLength={1}
            inputMode="numeric"
            autoComplete={index === 0 ? "one-time-code" : "off"}
            onChange={(event) => handleDigitInput(index, event.target.value)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            className="h-12 w-12 rounded-lg border border-slate-700 bg-slate-950 text-center text-lg font-semibold text-slate-100 outline-none focus:border-cyan-400"
          />
        ))}
      </div>

      {error ? <p className="text-sm text-rose-300">{error}</p> : null}
      {submitting ? <p className="text-sm text-slate-300">Verifying code...</p> : null}

      <button
        type="button"
        disabled={countdown > 0 || resending}
        onClick={() => {
          void handleResend();
        }}
        className="text-sm font-medium text-cyan-300 transition hover:text-cyan-200 disabled:cursor-not-allowed disabled:text-slate-500"
      >
        {countdown > 0
          ? `Resend code in ${countdown}s`
          : resending
            ? "Resending..."
            : "Resend code"}
      </button>
    </div>
  );
}
