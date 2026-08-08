let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!configured) return "";
  return trimTrailingSlash(configured);
}

function toAbsoluteUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalized}`;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
}

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const response = await fetch(toAbsoluteUrl("/auth/refresh"), {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        clearAccessToken();
        return null;
      }

      const payload = (await response.json()) as { access_token?: string };
      if (!payload.access_token) {
        clearAccessToken();
        return null;
      }

      setAccessToken(payload.access_token);
      return payload.access_token;
    } catch {
      clearAccessToken();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function ensureAccessToken(): Promise<string | null> {
  if (accessToken) return accessToken;
  return refreshAccessToken();
}

export async function authFetch(input: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const requestHeaders = new Headers(init.headers ?? {});
  const currentToken = accessToken;
  if (currentToken) {
    requestHeaders.set("Authorization", `Bearer ${currentToken}`);
  }

  const response = await fetch(toAbsoluteUrl(input), {
    ...init,
    headers: requestHeaders,
    credentials: "include",
  });

  if (response.status !== 401 || !retry) {
    return response;
  }

  const refreshedToken = await refreshAccessToken();
  if (!refreshedToken) return response;

  const retryHeaders = new Headers(init.headers ?? {});
  retryHeaders.set("Authorization", `Bearer ${refreshedToken}`);
  return fetch(toAbsoluteUrl(input), {
    ...init,
    headers: retryHeaders,
    credentials: "include",
  });
}
