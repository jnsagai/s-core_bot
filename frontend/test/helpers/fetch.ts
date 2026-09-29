/**
 * Route-based `fetch` mock and SSE response builder for component tests (no real network, no
 * browser). Every request URL is recorded so tests can assert same-origin paths only (FR-011).
 */
import { vi } from "vitest";

export type Handler = (init: RequestInit | undefined) => Response | Promise<Response>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function sse(events: { event: string; data: unknown }[], { hold = false } = {}): Response {
  const encoder = new TextEncoder();
  let id = 0;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const e of events) {
        id += 1;
        controller.enqueue(encoder.encode(`id: ${id}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`));
      }
      if (!hold) {
        controller.close();
      }
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

export const SNAPSHOT = "20260928T140548Z-7c6a05b3";

export const CAPABILITIES = {
  app: { name: "S-CORE Docs Assistant — Community Project", version: "0.1.0" },
  profile: "local",
  modes: {
    search: { available: true, reasons: [] },
    chat: { available: true, reasons: [] },
    compare: { available: false, reasons: ["not_implemented"] },
  },
  limits: {
    question_characters: 200,
    history_characters: 12000,
    active_generations: 1,
    queued_generations: 4,
    request_deadline_seconds: 120,
  },
  models: { generation: "qwen3:4b-instruct", embedding: "nomic-embed-text" },
};

export const SNAPSHOTS = {
  active: SNAPSHOT,
  snapshots: [
    {
      snapshot_id: SNAPSHOT, state: "active", active: true, created_at: "2026-09-28T14:05:48Z",
      semantic: "present", semantic_status: "enabled", chunks: 5658, documents: 635,
      sources: ["score-platform", "score-process"], limitations: [],
    },
    {
      snapshot_id: "20260928T135835Z-3e756999", state: "retired", active: false,
      created_at: "2026-09-28T13:58:35Z", semantic: "present", semantic_status: null,
      chunks: 5658, documents: 635, sources: ["score-platform", "score-process"], limitations: [],
    },
  ],
};

export const ENVELOPE = {
  schema_version: 1,
  request_id: "req-1",
  status: "answered",
  origin: "model",
  question: "How are inspections performed?",
  claims: [
    { text: "Inspections are formal reviews supported by a checklist.", kind: "documented", evidence_ids: ["E1"] },
    { text: "This suggests a checklist is mandatory.", kind: "interpretation", evidence_ids: ["E1"] },
    { text: "Tooling is not described.", kind: "limitation", evidence_ids: [] },
  ],
  limitations: ["Tooling is not described."],
  citations: [
    {
      evidence_id: "E1", chunk_id: "a".repeat(64), snapshot_id: SNAPSHOT, source_id: "score-process",
      revision: "66321fe6bd131eae58fbd6395b0f0b92d63e00f5", revision_status: "pinned",
      path: "process/general_concepts/score_review_concept.rst",
      heading_path: ["Review and Inspection Concept", "Inspection Definition"],
      line_start: 28, line_end: 29,
      excerpt: "Inspections are formal reviews supported by a checklist with documented conduct and outcome.",
      immutable_url: "https://github.com/eclipse-score/process_description/blob/66321fe6bd131eae58fbd6395b0f0b92d63e00f5/process/general_concepts/score_review_concept.rst#L28-L29",
      revision_match: "exact",
    },
  ],
  snapshot_id: SNAPSHOT,
  model: { provider: "ollama", name: "qwen3:4b-instruct", digest: "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0", runtime_version: "0.34.0" },
  retrieval: { mode: "hybrid", degraded_reason: null, results: 8, evidence_supplied: 8, evidence_dropped: 0 },
  warnings: [],
  policy_version: 1,
  timings_ms: { total: 1000 },
};

export interface FetchMock {
  calls: { url: string; init?: RequestInit }[];
  routes: Record<string, Handler>;
}

export function installFetch(routes: Record<string, Handler>): FetchMock {
  const mock: FetchMock = { calls: [], routes };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      mock.calls.push({ url, init });
      const key = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
      const handler = mock.routes[key];
      if (!handler) {
        return json({ error: { code: "NOT_FOUND", message: `no mock for ${key}`, request_id: "", retryable: false } }, 404);
      }
      if (init?.signal?.aborted) {
        throw new DOMException("aborted", "AbortError");
      }
      return handler(init);
    }),
  );
  return mock;
}

export function baseRoutes(overrides: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    "GET /api/v1/capabilities": () => json(CAPABILITIES),
    "GET /health/ready": () => json({ ready: true, capabilities: CAPABILITIES.modes }),
    "GET /api/v1/snapshots": () => json(SNAPSHOTS),
    ...overrides,
  };
}
