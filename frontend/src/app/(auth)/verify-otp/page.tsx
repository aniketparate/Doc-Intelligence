"use client";

import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { OtpInput } from "@/components/auth/OtpInput";

function VerifyOtpContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const email = searchParams.get("email") ?? "";
  const purposeParam = searchParams.get("purpose");
  const purpose = useMemo(
    () => (purposeParam === "verify_email" ? "verify_email" : "login"),
    [purposeParam],
  );

  if (!email) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-10">
        <h1 className="text-3xl font-semibold text-white">Verify code</h1>
        <p className="mt-4 text-sm text-rose-300">Missing email in URL. Start from register or login.</p>
        <Link href="/login" className="mt-6 text-sm font-medium text-cyan-300 hover:text-cyan-200">
          Back to login
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-10">
      <h1 className="text-3xl font-semibold text-white">Verify code</h1>
      <p className="mt-2 text-sm text-slate-300">
        Enter the 6-digit code sent to <span className="font-medium text-white">{email}</span>.
      </p>
      <div className="mt-8 rounded-2xl border border-slate-700/60 bg-slate-900/70 p-6 backdrop-blur">
        <OtpInput
          email={email}
          purpose={purpose}
          onVerified={() => {
            router.replace("/dashboard");
          }}
        />
      </div>
    </main>
  );
}

export default function VerifyOtpPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-10">
          <h1 className="text-3xl font-semibold text-white">Verify code</h1>
          <p className="mt-4 text-sm text-slate-300">Preparing verification...</p>
        </main>
      }
    >
      <VerifyOtpContent />
    </Suspense>
  );
}
