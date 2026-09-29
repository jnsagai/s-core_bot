/**
 * SSE-over-`fetch()` reader shared by chat and comparison (F005/F007 contracts). `EventSource`
 * cannot POST a body or set `Accept`, and it silently reconnects, which both contracts forbid.
 * This reads `response.body` itself and never retries.
 */
export interface SseEvent {
  event: string;
  id: number;
  data: Record<string, unknown>;
}

export function parseFrame(frame: string): SseEvent | null {
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
  return { event, id, data: JSON.parse(data) as Record<string, unknown> };
}

/** Yields parsed events until the stream ends; the caller aborts through the fetch signal. */
export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
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
        const parsed = parseFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (parsed) {
          yield parsed;
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
