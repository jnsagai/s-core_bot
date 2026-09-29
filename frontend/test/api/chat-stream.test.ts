import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "../../src/api/chat";

function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

const PROGRESS_QUEUED = 'id: 1\nevent: progress\ndata: {"stage":"queued","position":1}\n\n';
const PROGRESS_SEARCHING = 'id: 2\nevent: progress\ndata: {"stage":"searching"}\n\n';
const ANSWER = 'id: 3\nevent: answer\ndata: {"status":"answered"}\n\n';
const DONE = "id: 4\nevent: done\ndata: {}\n\n";
const ERROR = 'id: 5\nevent: error\ndata: {"error":{"code":"ANSWER_INVALID"}}\n\n';

describe("streamChat", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("yields progress, answer, done events in order with increasing ids", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(sseResponse([PROGRESS_QUEUED, PROGRESS_SEARCHING, ANSWER, DONE]));
    vi.stubGlobal("fetch", fetchMock);

    const events = [];
    for await (const event of streamChat({ question: "hi" })) {
      events.push(event);
    }

    expect(events.map((e) => e.event)).toEqual(["progress", "progress", "answer", "done"]);
    expect(events.map((e) => e.id)).toEqual([1, 2, 3, 4]);
    expect(events[2].data).toEqual({ status: "answered" });
  });

  it("yields an error event followed by done on a midstream failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(sseResponse([PROGRESS_QUEUED, ERROR, DONE]));
    vi.stubGlobal("fetch", fetchMock);

    const events = [];
    for await (const event of streamChat({ question: "hi" })) {
      events.push(event);
    }

    expect(events.map((e) => e.event)).toEqual(["progress", "error", "done"]);
  });

  it("handles a frame split across multiple stream chunks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse(['id: 1\nevent: progress\n', 'data: {"stage":"queued"}\n\n', DONE]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events = [];
    for await (const event of streamChat({ question: "hi" })) {
      events.push(event);
    }

    expect(events.map((e) => e.event)).toEqual(["progress", "done"]);
  });

  it("passes the abort signal through to fetch and sends the SSE Accept header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([DONE]));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    for await (const _event of streamChat({ question: "hi" }, controller.signal)) {
      // drain
    }

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.signal).toBe(controller.signal);
    expect((init.headers as Record<string, string>).Accept).toBe("text/event-stream");
  });

  it("never reconnects: stops after the stream closes even without a done event", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([PROGRESS_QUEUED]));
    vi.stubGlobal("fetch", fetchMock);

    const events = [];
    for await (const event of streamChat({ question: "hi" })) {
      events.push(event);
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(events.map((e) => e.event)).toEqual(["progress"]);
  });
});
