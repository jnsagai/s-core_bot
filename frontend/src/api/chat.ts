/**
 * `POST /api/v1/chat`, JSON or SSE-over-`fetch()` (research.md R3): `EventSource` cannot POST a
 * body or set `Accept`, and it silently reconnects, which F005's contract forbids. This module
 * reads `response.body` itself and never retries.
 */
import { apiFetch, apiFetchJson } from "./client";
import { readSse } from "./sse";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  snapshotId?: string;
}

export interface ChatRequest {
  question: string;
  snapshotId?: string | null;
  history?: ChatTurn[];
}

export type ChatStreamEvent =
  | { event: "progress"; id: number; data: { stage: string; position?: number } }
  | { event: "answer"; id: number; data: Record<string, unknown> }
  | { event: "error"; id: number; data: Record<string, unknown> }
  | { event: "done"; id: number; data: Record<string, never> };

function toRequestBody(request: ChatRequest): Record<string, unknown> {
  const body: Record<string, unknown> = { question: request.question };
  if (request.snapshotId !== undefined) {
    body.snapshot_id = request.snapshotId;
  }
  if (request.history !== undefined) {
    body.history = request.history.map((turn) => {
      const out: Record<string, unknown> = { role: turn.role, content: turn.content };
      if (turn.snapshotId !== undefined) {
        out.snapshot_id = turn.snapshotId;
      }
      return out;
    });
  }
  return body;
}

/** JSON (non-streaming) chat call. */
export async function chat(request: ChatRequest): Promise<Record<string, unknown>> {
  return apiFetchJson("/api/v1/chat", { method: "POST", body: toRequestBody(request) });
}

/**
 * Streams `POST /api/v1/chat` with `Accept: text/event-stream`. Aborting `signal` stops iteration
 * immediately with no reconnect and no further events — cancellation is the only control this
 * function offers (F005 FR-020).
 */
export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const response = await apiFetch("/api/v1/chat", {
    method: "POST",
    body: toRequestBody(request),
    accept: "text/event-stream",
    signal,
  });
  for await (const event of readSse(response)) {
    yield event as ChatStreamEvent;
  }
}
