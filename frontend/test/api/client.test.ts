import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, apiFetchJson } from "../../src/api/client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds a relative same-origin URL and returns the response on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetchJson("/api/v1/capabilities");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe("/api/v1/capabilities");
    expect(calledUrl.startsWith("http://") || calledUrl.startsWith("https://")).toBe(false);
    expect(init.method).toBe("GET");
  });

  it("sends a JSON body and Content-Type for POST requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/search", { method: "POST", body: { query: "hello" } });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ query: "hello" }));
  });

  it("sends the Accept header for streaming requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/chat", {
      method: "POST",
      body: { question: "hi" },
      accept: "text/event-stream",
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Accept).toBe("text/event-stream");
  });

  it("parses the F001 error envelope and throws ApiError on a non-2xx status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(429, {
        error: {
          code: "CHAT_BUSY",
          message: "Too many requests.",
          request_id: "req-123",
          retryable: true,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetchJson("/api/v1/chat")).rejects.toMatchObject({
      code: "CHAT_BUSY",
      requestId: "req-123",
      retryable: true,
      status: 429,
    });
  });

  it("falls back to a generic error when the error body is not valid JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("not json", { status: 500, statusText: "Internal Server Error" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetchJson("/api/v1/capabilities")).rejects.toBeInstanceOf(ApiError);
  });
});
