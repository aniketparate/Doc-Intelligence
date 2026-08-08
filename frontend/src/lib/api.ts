import { authFetch, getApiBaseUrl } from "@/lib/auth";

type ApiMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

type ApiRequestOptions<TBody> = {
  method?: ApiMethod;
  body?: TBody;
  headers?: HeadersInit;
  auth?: boolean;
  signal?: AbortSignal;
};

type ErrorPayload = {
  detail?: string;
  message?: string;
};

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function toAbsoluteUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalized}`;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  if (!text) return null;
  return text;
}

export async function apiRequest<TResponse, TBody = undefined>(
  path: string,
  options: ApiRequestOptions<TBody> = {},
): Promise<TResponse> {
  const { method = "GET", body, headers, auth = false, signal } = options;

  const requestHeaders = new Headers(headers ?? {});
  let requestBody: BodyInit | undefined;

  if (body !== undefined) {
    if (body instanceof FormData) {
      requestBody = body;
    } else {
      requestHeaders.set("Content-Type", "application/json");
      requestBody = JSON.stringify(body);
    }
  }

  const requestInit: RequestInit = {
    method,
    headers: requestHeaders,
    body: requestBody,
    signal,
    credentials: "include",
  };

  const response = auth
    ? await authFetch(path, requestInit)
    : await fetch(toAbsoluteUrl(path), requestInit);
  const payload = await parseResponseBody(response);

  if (!response.ok) {
    const messageFromPayload =
      typeof payload === "object" && payload !== null
        ? ((payload as ErrorPayload).detail ?? (payload as ErrorPayload).message)
        : undefined;
    throw new ApiError(response.status, messageFromPayload ?? "Request failed", payload);
  }

  return payload as TResponse;
}
