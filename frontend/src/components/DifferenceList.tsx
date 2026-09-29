import type { CitationViewModel } from "../answer/model";
import { coverageText, TYPE_LABELS, type ComparisonViewModel } from "../comparison/model";

/** Typed differences with per-side evidence buttons (F007 FR-004, FR-018). Evidence IDs resolve
 * only within their own side, so an `L` button always opens a left-snapshot excerpt. */
export function DifferenceList({
  result,
  onOpenCitation,
}: {
  result: ComparisonViewModel;
  onOpenCitation: (citation: CitationViewModel) => void;
}) {
  const left = new Map(result.evidence.left.map((c) => [c.evidenceId, c]));
  const right = new Map(result.evidence.right.map((c) => [c.evidenceId, c]));
  const button = (id: string, citation: CitationViewModel | undefined, side: string) =>
    citation ? (
      <button
        key={id}
        type="button"
        className="citation-marker"
        aria-label={`Open ${side} evidence ${id}: ${citation.title}`}
        onClick={() => onOpenCitation(citation)}
      >
        [{id}]
      </button>
    ) : null;
  if (result.differences.length === 0) {
    return <p>No differences were reported for this question.</p>;
  }
  return (
    <ul className="differences">
      {result.differences.map((d, index) => {
        const why = coverageText(d);
        return (
          <li key={index} className={`difference difference-${d.type}`}>
            <strong>{TYPE_LABELS[d.type]}</strong>
            {why && <span className="muted"> ({why})</span>}: {d.statement}{" "}
            {d.leftEvidenceIds.map((id) => button(id, left.get(id), "left"))}
            {d.rightEvidenceIds.map((id) => button(id, right.get(id), "right"))}
          </li>
        );
      })}
    </ul>
  );
}
