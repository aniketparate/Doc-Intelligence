import Link from "next/link";

import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-10">
      <h1 className="text-3xl font-semibold text-white">Sign in</h1>
      <p className="mt-2 text-sm text-slate-300">Access your projects and continue your analysis sessions.</p>
      <div className="mt-8 rounded-2xl border border-slate-700/60 bg-slate-900/70 p-6 backdrop-blur">
        <LoginForm />
      </div>
      <p className="mt-4 text-center text-sm text-slate-400">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="font-medium text-cyan-300 hover:text-cyan-200">
          Create one
        </Link>
      </p>
    </main>
  );
}
