# Data Model: F006 Local Web Experience and Privacy

All records below are client-side TypeScript types under `frontend/src/`. F006 adds **no** new
server-side domain record and **no** new persistence: nothing here is written to a database,
`localStorage`, `sessionStorage`, `IndexedDB`, or a cookie. Everything lives in React state and is
discarded on reload or an explicit "new conversation" action (FR-013).

## ConversationTurn (`frontend/src/state/conversation.ts`)

In-memory only.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | client-generated (e.g. `crypto.randomUUID()`), for React keys and focus management only |
| `role` | `"user" \| "assistant"` | matches F005's `history` turn shape |
| `content` | string | for a `user` turn, the literal question; for `assistant`, the rendered answer text used only for follow-up history composition, never re-parsed as evidence |
| `snapshotId` | string \| null | set on `assistant` turns from the envelope's `snapshot_id`; omitted on `user` turns |
| `answer` | `AnswerViewModel \| null` | present only on a completed `assistant` turn |
| `status` | `"queued" \| "searching" \| "generating" \| "validating" \| "ready" \| "cancelled" \| "failed"` | drives `StatusBadge`; transient during generation, `"ready"`/`"failed"`/`"cancelled"` once settled |

`ConversationState` is `{ snapshotId: string | null; turns: ConversationTurn[] }`. Reload or "New
conversation" replaces it with the initial empty state — no merge, no partial retention.

## AnswerViewModel (`frontend/src/components/AnswerView.tsx`)

Derived, not stored separately, from an F005 `AnswerEnvelope`
(`specs/005-grounded-chat/contracts/http-api.md`) — a display-shaped read of the same fields:

| Field | Type | Source |
| --- | --- | --- |
| `requestId` | string | `request_id` |
| `status` | F005 answer status | `status` |
| `origin` | `"model" \| "extractive_fallback"` | `origin` |
| `claims` | `{ text, kind, citationIds: string[] }[]` | `claims[].evidence_ids` mapped to citation markers |
| `limitations` | string[] | `limitations` |
| `citations` | `CitationViewModel[]` | `citations` (see below) |
| `snapshotId` | string | `snapshot_id` |
| `model` | `{ provider, name, digest }` | `model` |
| `warnings` | string[] | `warnings` |

## CitationViewModel (`frontend/src/components/EvidencePanel.tsx`)

| Field | Type | Source |
| --- | --- | --- |
| `evidenceId` | string | `evidence_id` |
| `title` / `headingPath` | string / string[] | derived from `path` + `heading_path` |
| `sourceId`, `revision`, `revisionStatus` | string | as returned |
| `excerpt` | string | `excerpt` (already sanitized server-side text; still rendered through `SafeMarkdown`) |
| `lineStart` / `lineEnd` | number \| null | `line_start` / `line_end` |
| `upstreamUrl` | string \| null | `immutable_url` |
| `revisionMatch` | `"exact" \| "unverified" \| "none"` | `revision_match` — controls the label shown next to `upstreamUrl` |

Identical shape is reused for a direct `GET /api/v1/citations/{snapshot}/{chunk}` lookup
(F004 `CitationRecord`) when a citation is opened without an in-hand envelope (e.g. from a search
result rather than a chat answer).

## AppReadinessState (`frontend/src/state/readiness.ts`)

| Field | Type | Source |
| --- | --- | --- |
| `search` | `{ available: boolean; degradedReason: string \| null }` | `/api/v1/capabilities.modes.search` + `/health/ready` |
| `chat` | `{ available: boolean; reason: string \| null }` | `/api/v1/capabilities.modes.chat` |
| `limits` | `{ questionCharacters: number; historyCharacters: number }` | `/api/v1/capabilities.limits` (A-037: never hardcoded) |
| `snapshots` | `SnapshotSummary[]`, `activeSnapshotId: string \| null` | `/api/v1/snapshots` |
| `fetchedAt` | number (epoch ms) | client clock, for the settings view only — not a cache-invalidation timer (A-036: no polling) |

Refetched only per A-036 (initial load; explicit reload; error-state Retry; opening settings).

## ExportDocument (`frontend/src/components/ExportMenu.tsx`)

Built at export time from the current `AnswerViewModel`; never stored, only serialized to a
`Blob` for download.

**Markdown shape**:

```markdown
# Question

<question text>

# Answer (<status>)

- **[documented]** <claim text> [E1]
...

## Citations

- **E1** — <title> § <heading path> (rev <revision>) — <excerpt>
  <upstream url, if any, labelled with revisionMatch>

---
Snapshot: <snapshotId> · Model: <provider>/<name> (<digest>)
```

**JSON shape**: `{ question, status, origin, claims, limitations, citations, snapshotId, model,
exportedAt }` — a strict subset of the envelope's own fields, so nothing is invented and nothing
machine-specific (no file paths, no environment values, no headers) is ever included. `exportedAt`
is an ISO-8601 client timestamp, added only for the user's own reference.
