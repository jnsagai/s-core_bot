import type { CitationViewModel } from "../answer/model";
import { Dialog } from "./Dialog";
import { SafeMarkdown } from "./SafeMarkdown";

const MATCH_LABELS = {
  exact: "exact revision",
  unverified: "revision not verified",
  none: "no upstream link",
} as const;

/** A citation's stored excerpt and provenance (FR-007, FR-008). The local excerpt never depends on
 * the upstream link being reachable. */
export function EvidencePanel({
  citation,
  onClose,
}: {
  citation: CitationViewModel;
  onClose: () => void;
}) {
  const lines =
    citation.lineStart !== null
      ? `lines ${citation.lineStart}${citation.lineEnd !== null && citation.lineEnd !== citation.lineStart ? `–${citation.lineEnd}` : ""}`
      : "lines unknown";
  const title = citation.evidenceId ? `${citation.evidenceId} · ${citation.title}` : citation.title;
  return (
    <Dialog title={title} onClose={onClose}>
      <dl className="provenance">
        <dt>Section</dt>
        <dd>{citation.headingPath.join(" › ") || "—"}</dd>
        <dt>Source</dt>
        <dd>
          {citation.sourceId} · {citation.path} · {lines}
        </dd>
        <dt>Revision</dt>
        <dd>
          <code>{citation.revision.slice(0, 12)}</code> ({citation.revisionStatus})
        </dd>
      </dl>
      <div className="excerpt">
        <SafeMarkdown text={citation.excerpt} />
      </div>
      {citation.upstreamUrl ? (
        <p>
          <a href={citation.upstreamUrl} target="_blank" rel="noopener noreferrer">
            Open upstream source
          </a>{" "}
          ({MATCH_LABELS[citation.revisionMatch]})
        </p>
      ) : (
        <p className="muted">No upstream link: {MATCH_LABELS[citation.revisionMatch]}.</p>
      )}
      <button type="button" onClick={onClose}>
        Close
      </button>
    </Dialog>
  );
}
