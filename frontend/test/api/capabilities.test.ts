import { afterEach, describe, expect, it, vi } from "vitest";
import { getCapabilities, getHealthReady } from "../../src/api/capabilities";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("getCapabilities", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("maps snake_case limits to camelCase", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          app: { name: "S-CORE Docs Assistant", version: "0.1.0" },
          runs_locally: true,
          modes: { search: { available: true, reasons: [] }, chat: { available: false, reasons: ["model_missing"] } },
          limits: {
            question_characters: 4000,
            history_characters: 12000,
            active_generations: 1,
            queued_generations: 4,
            request_deadline_seconds: 120,
          },
          models: { generation: "qwen3:4b-instruct", embedding: "nomic-embed-text" },
          response_languages: ["en"],
        }),
      ),
    );

    const result = await getCapabilities();
    expect(result.limits.questionCharacters).toBe(4000);
    expect(result.limits.historyCharacters).toBe(12000);
    expect(result.modes.chat.available).toBe(false);
    expect(result.modes.chat.reasons).toEqual(["model_missing"]);
  });
});

describe("getHealthReady", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the body even on a 503 not-ready response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(503, { ready: false, capabilities: { chat: { available: false, reasons: ["model_missing"] } } }),
      ),
    );

    const result = await getHealthReady();
    expect(result.ready).toBe(false);
    expect(result.capabilities.chat.available).toBe(false);
  });
});
