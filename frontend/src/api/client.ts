/**
 * The only module allowed to call `fetch`. Every path is a same-origin relative path under
 * `/api/v1/*` or `/health/*` — there is no configurable base URL, so an audit of FR-011
 * (specs/006-local-web-ui/spec.md) is "read this file" (research.md R1).
 */

export interface ApiErrorPayload {
  code: string;
  message: string;
  requestId: string;
  retryable: boolean;
}

export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string;
  readonly retryable: boolean;
  readonly status: number;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code;
    this.requestId = payload.requestId;
    this.retryable = payload.retryable;
  }
}

type ApiPath = `/api/v1/${string}` | `/health/${string}`;

async function parseErrorPayload(response: Response): Promise<ApiErrorPayload> {
  try {
    const body = (await response.json()) as { error?: Record<string, unknown> };
    const error = body.error ?? {};
    return {
      code: typeof error.code === "string" ? error.code : "UNKNOWN_ERROR",
      message: typeof error.message === "string" ? error.message : response.statusText,
      requestId: typeof error.request_id === "string" ? error.request_id : "",
      retryable: error.retryable === true,
    };
  } catch {
    return { code: "UNKNOWN_ERROR", message: response.statusText, requestId: "", retryable: false };
  }
}

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  accept?: string;
  /** Extra statuses to treat as success beyond 2xx (e.g. `/health/ready`'s 503-when-not-ready,
   * which is still a well-formed body, not an F001 error envelope). */
  okStatuses?: number[];
}

/** Issues a same-origin request and returns the raw `Response` (callers decide how to read the
 * body — JSON for most calls, a stream for chat SSE). Throws `ApiError` on a non-2xx status. */
export async function apiFetch(path: ApiPath, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.accept) {
    headers.Accept = options.accept;
  }
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers,
    body,
    signal: options.signal,
  });
  if (!response.ok && !options.okStatuses?.includes(response.status)) {
    throw new ApiError(response.status, await parseErrorPayload(response));
  }
  return response;
}

export async function apiFetchJson<T>(path: ApiPath, options: RequestOptions = {}): Promise<T> {
  const response = await apiFetch(path, options);
  return (await response.json()) as T;
}
