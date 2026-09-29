import type { AnswerViewModel, CitationViewModel } from "../answer/model";

const STATUS_TEXT: Record<string, string> = {
  answered: "Answered from the cited sources",
  partial: "Evidence incomplete — only part of the question is answered",
  insufficient_evidence: "The documentation does not answer this question",
  clarification_needed: "More context is needed",
};

/** Claims grouped by kind with citation markers (FR-007); interpretations and limitations are
 * labelled so they are never mistaken for documented facts. */
export function AnswerView({
  answer,
  onOpenCitation,
}: {
  answer: AnswerViewModel;
  onOpenCitation: (citation: CitationViewModel) => void;
}) {
  const byId = new Map(answer.citations.map((c) => [c.evidenceId, c]));
  const facts = answer.claims.filter((c) => c.kind !== "limitation");
  return (
    <div className="answer">
      <p className={`answer-status answer-${answer.status}`}>
        {STATUS_TEXT[answer.status] ?? answer.status}
      </p>
      {answer.origin === "extractive_fallback" && (
        <p className="notice">
          The model's answer failed validation; these are the most relevant excerpts, not a
          composed answer.
        </p>
      )}
      {facts.length > 0 && (
        <ul className="claims">
          {facts.map((claim, index) => (
            <li key={index} className={`claim claim-${claim.kind}`}>
              {claim.kind === "interpretation" && <strong>Interpretation: </strong>}
              {claim.text}{" "}
              {claim.citationIds.map((id) => {
                const citation = byId.get(id);
                return citation ? (
                  <button
                    key={id}
                    type="button"
                    className="citation-marker"
                    aria-label={`Open citation ${id}: ${citation.title}`}
                    onClick={() => onOpenCitation(citation)}
                  >
                    [{id}]
                  </button>
                ) : null;
              })}
            </li>
          ))}
        </ul>
      )}
      {answer.limitations.length > 0 && (
        <div className="limitations">
          <h3>Limitations</h3>
          <ul>
            {answer.limitations.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </div>
      )}
      {answer.citations.length > 0 && (
        <div className="sources">
          <h3>Sources</h3>
          <ul>
            {answer.citations.map((citation) => (
              <li key={citation.evidenceId}>
                <button type="button" onClick={() => onOpenCitation(citation)}>
                  [{citation.evidenceId}] {citation.title}
                </button>{" "}
                <span className="muted">
                  {citation.sourceId} · {citation.path}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.model && (
        <p className="muted small">
          Snapshot {answer.snapshotId} · model {answer.model.name} ({answer.model.digest.slice(0, 12)})
        </p>
      )}
    </div>
  );
}
