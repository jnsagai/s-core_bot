# UI Contract: F006 Local Web Experience and Privacy

F006 adds no new HTTP endpoint. This contract covers (a) how the frontend consumes the existing
F001/F004/F005 contracts, and (b) the one backend surface this feature does add: static serving
and the narrowed guard exemption.

## 1. Frontend → backend calls (FR-011)

The built frontend issues requests only to:

- `GET /health/live`, `GET /health/ready`
- `GET /api/v1/capabilities`
- `GET /api/v1/snapshots`
- `GET /api/v1/sources?snapshot_id=...`
- `POST /api/v1/search`
- `POST /api/v1/chat` (JSON, or SSE via `Accept: text/event-stream`)
- `GET /api/v1/citations/{snapshot_id}/{chunk_id}`
- `GET /api/v1/entities?id=...`, `GET /api/v1/relationships?key=...` (search screen, "related"
  navigation only if surfaced — optional per spec FR-018, not required)

All requests are same-origin (relative paths, e.g. `fetch("/api/v1/search", ...)`); there is no
build-time or runtime "API base URL" setting. `frontend/src/api/client.ts` is the single module
allowed to call `fetch`; every other module goes through it, so a future code review can audit
FR-011 by checking one file.

No request ever targets the local model runtime, a filesystem path, or any other host. No
request carries a cookie or an `Authorization` header (none exists in this baseline).

## 2. New backend surface: static document serving

### `GET /` and `GET /assets/*` (and any other file actually present in `frontend/dist/`)

Served by `StaticFiles(directory="frontend/dist", html=True)` mounted after all `/api/v1/*` and
`/health/*` routers (research.md R4). Response headers add `cache-control: no-store` for `/`
(the HTML shell may reference build-specific asset hashes and must not be served stale) and the
default long-lived caching Starlette applies to hashed asset files under `/assets/*` is
acceptable (their filenames change on every build). No `x-request-id` header is required for
static assets (no F001 access-log correlation need beyond the existing body-free log).

The `/` response additionally carries (FR-010a):

```text
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
  form-action 'self'
```

If `frontend/dist/` does not exist (backend built without a frontend bundle — e.g. a pure-API
deployment), `GET /` returns a plain honest `503` with a short message ("frontend bundle not
built") rather than a stack trace or an empty `200`.

### Guard change: `HostOriginGuard` (research.md R5, FR-011a)

```text
Before (F001):                              After (F006):
  any Sec-Fetch-Site: cross-site → 403        Sec-Fetch-Site: cross-site AND
                                                 (method != GET OR path not in {"/", "/assets/*"})
                                                 → 403
                                               Sec-Fetch-Site: cross-site AND
                                                 method == GET AND path in {"/", "/assets/*"}
                                                 → allowed through to StaticFiles
  Host check: unchanged, always applied         Host check: unchanged, always applied
```

`/api/v1/*` and `/health/*` are never in `{"/", "/assets/*"}`, so this table has no effect on any
existing F001/F004/F005 test or acceptance scenario (AT-18 stays exactly as strict).

## 3. Client-side contract for chat streaming (research.md R3)

`chat.ts` exposes `parseChatStream(response: Response): AsyncGenerator<ChatStreamEvent>` where
`ChatStreamEvent` mirrors the F005 SSE contract exactly:

```ts
type ChatStreamEvent =
  | { event: "progress"; id: number; data: { stage: "queued" | "searching" | "generating" | "validating"; position?: number } }
  | { event: "answer"; id: number; data: AnswerEnvelope }
  | { event: "error"; id: number; data: ErrorEnvelope }
  | { event: "done"; id: number; data: Record<string, never> };
```

Consumers (`ChatPanel.tsx`) `for await` this generator; an `AbortController` passed into `fetch`
is the only cancellation mechanism — there is no reconnect logic anywhere in this module, per
F005's "browsers must not reconnect and silently duplicate inference."

## 4. Export contract (FR-016)

`ExportMenu.tsx` calls `buildMarkdownExport(turn: ConversationTurn): string` and
`buildJsonExport(turn: ConversationTurn): ExportDocument` (data-model.md), then:

```ts
const blob = new Blob([content], { type: mimeType }); // "text/markdown" | "application/json"
const url = URL.createObjectURL(blob);
// trigger <a href={url} download={filename}>.click(), then URL.revokeObjectURL(url)
```

`filename` is derived only from the snapshot ID and a client timestamp (e.g.
`score-answer-20260928T220000Z.md`) — never from a server-provided file path.
