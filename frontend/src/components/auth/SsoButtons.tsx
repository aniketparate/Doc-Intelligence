import { getApiBaseUrl } from "@/lib/auth";

const ssoButtonClass =
  "inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-slate-500 hover:bg-slate-700";

export function SsoButtons() {
  const baseUrl = getApiBaseUrl();

  return (
    <div className="flex flex-col gap-2">
      <a className={ssoButtonClass} href={`${baseUrl}/auth/sso/google`}>
        Continue with Google
      </a>
      <a className={ssoButtonClass} href={`${baseUrl}/auth/sso/github`}>
        Continue with GitHub
      </a>
    </div>
  );
}
