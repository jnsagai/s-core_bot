import { RELATION_LABELS, type SnapshotDiffViewModel } from "../comparison/model";

const short = (revision: string | null) => (revision ? revision.slice(0, 12) : "—");

/** Per-source identity of both snapshots (SRC-003): revisions and their status, never a release
 * label, with metadata warnings shown as they are. */
export function SnapshotDiffTable({ diff }: { diff: SnapshotDiffViewModel }) {
  return (
    <div className="snapshot-diff">
      <table>
        <caption>What is being compared</caption>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Left revision</th>
            <th scope="col">Right revision</th>
            <th scope="col">Relation</th>
          </tr>
        </thead>
        <tbody>
          {diff.sources.map((row) => (
            <tr key={row.sourceId}>
              <th scope="row">{row.sourceId}</th>
              <td>
                <code>{short(row.leftRevision)}</code> {row.leftRevisionStatus && `(${row.leftRevisionStatus})`}
              </td>
              <td>
                <code>{short(row.rightRevision)}</code> {row.rightRevisionStatus && `(${row.rightRevisionStatus})`}
              </td>
              <td>{RELATION_LABELS[row.relation]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">No release label: per-source revisions identify each snapshot.</p>
      {diff.processing.length > 0 && (
        <p className="muted small">
          Processing differs: {diff.processing.map((p) => `${p.field} (${p.left ?? "—"} → ${p.right ?? "—"})`).join("; ")}
        </p>
      )}
      {diff.warnings.length > 0 && (
        <ul className="notice">
          {diff.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
