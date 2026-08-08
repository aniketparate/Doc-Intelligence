import Link from "next/link";

import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-10">
      <h1 className="text-3xl font-semibold text-white">Create your account</h1>
      <p className="mt-2 text-sm text-slate-300">Start a workspace for your document intelligence projects.</p>
      <div className="mt-8 rounded-2xl border border-slate-700/60 bg-slate-900/70 p-6 backdrop-blur">
        <RegisterForm />
      </div>
      <p className="mt-4 text-center text-sm text-slate-400">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-cyan-300 hover:text-cyan-200">
          Sign in
        </Link>
      </p>
    </main>
  );
}
