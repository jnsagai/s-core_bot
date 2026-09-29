/**
 * `POST /api/v1/compare` (JSON or SSE) and `GET /api/v1/snapshots/diff`
 * (specs/007-version-comparison/contracts/http-api.md). Streaming never reconnects; aborting the
 * signal is the only control (the server then releases the generation slot and both pins).
 */
import { apiFetch, apiFetchJson } from "./client";
import { readSse, type SseEvent } from "./sse";

export interface CompareRequest {
  question: string;
  leftSnapshotId: string;
  rightSnapshotId: string;
}

export type CompareStreamEvent = SseEvent;

function toBody(request: CompareRequest): Record<string, unknown> {
  return {
    question: request.question,
    left_snapshot_id: request.leftSnapshotId,
    right_snapshot_id: request.rightSnapshotId,
  };
}

export async function compare(request: CompareRequest): Promise<Record<string, unknown>> {
  return apiFetchJson("/api/v1/compare", { method: "POST", body: toBody(request) });
}

export async function* streamCompare(
  request: CompareRequest,
  signal?: AbortSignal,
): AsyncGenerator<CompareStreamEvent> {
  const response = await apiFetch("/api/v1/compare", {
    method: "POST",
    body: toBody(request),
    accept: "text/event-stream",
    signal,
  });
  yield* readSse(response);
}

export async function getSnapshotDiff(left: string, right: string): Promise<Record<string, unknown>> {
  const query = `left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`;
  return apiFetchJson(`/api/v1/snapshots/diff?${query}` as `/api/v1/${string}`);
}
