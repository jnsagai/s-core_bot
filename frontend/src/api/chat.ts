/**
 * `POST /api/v1/chat`, JSON or SSE-over-`fetch()` (research.md R3): `EventSource` cannot POST a
 * body or set `Accept`, and it silently reconnects, which F005's contract forbids. This module
 * reads `response.body` itself and never retries.
 */
import { apiFetch, apiFetchJson } from "./client";

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

function parseFrame(frame: string): ChatStreamEvent | null {
  let id: number | null = null;
  let event: string | null = null;
  let data: string | null = null;
  for (const line of frame.split("\n")) {
    if (line.startsWith("id:")) {
      id = Number(line.slice(3).trim());
    } else if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data = line.slice(5).trim();
    }
  }
  if (id === null || event === null || data === null) {
    return null;
  }
  const parsed = JSON.parse(data) as Record<string, unknown>;
  return { event, id, data: parsed } as ChatStreamEvent;
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
  const body = response.body;
  if (!body) {
    return;
  }
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsedEvent = parseFrame(frame);
        if (parsedEvent) {
          yield parsedEvent;
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
