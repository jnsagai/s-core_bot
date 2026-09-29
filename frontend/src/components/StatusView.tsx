import type { AppReadinessState } from "../state/readiness";

/** Settings/status view (FR-001): readiness, models and limits. Re-checks only when asked. */
export function StatusView({ readiness, onRefresh }: { readiness: AppReadinessState; onRefresh: () => void }) {
  return (
    <section aria-labelledby="status-heading">
      <h2 id="status-heading">Status</h2>
      <dl className="provenance">
        <dt>Search</dt>
        <dd>
          {readiness.search.available ? "available" : "unavailable"}
          {readiness.search.degradedReason ? ` (keyword-only: ${readiness.search.degradedReason})` : ""}
        </dd>
        <dt>Answers</dt>
        <dd>
          {readiness.chat.available ? "available" : `unavailable${readiness.chat.reason ? ` (${readiness.chat.reason})` : ""}`}
        </dd>
        <dt>Answer model</dt>
        <dd>{readiness.models?.generation ?? "unknown"}</dd>
        <dt>Embedding model</dt>
        <dd>{readiness.models?.embedding ?? "unknown"}</dd>
        <dt>Question limit</dt>
        <dd>{readiness.limits ? `${readiness.limits.questionCharacters} characters` : "unknown"}</dd>
        <dt>Snapshots</dt>
        <dd>{readiness.snapshots.length}</dd>
      </dl>
      <button type="button" onClick={onRefresh}>
        Check again
      </button>
    </section>
  );
}
