import type { CitationViewModel } from "../answer/model";
import { coverageText, TYPE_LABELS, RELATION_LABELS, type ComparisonViewModel } from "./model";

/** Markdown/JSON export of a comparison (F007 FR-019). Only result fields are used, so no machine
 * path, environment value or credential can appear; both snapshot identities are always kept. */
function citationLine(c: CitationViewModel): string {
  const section = c.headingPath.length ? ` § ${c.headingPath.join(" › ")}` : "";
  const link = c.upstreamUrl ? ` — ${c.upstreamUrl}` : "";
  return `- **${c.evidenceId}** — ${c.sourceId}:${c.path}${section} (rev ${c.revision.slice(0, 12)}, ${c.revisionStatus})${link}`;
}

export function buildComparisonMarkdown(result: ComparisonViewModel): string {
  const s = result.snapshots;
  const lines = [
    "# Comparison",
    "",
    result.question,
    "",
    `- Left snapshot: ${s.leftSnapshotId} (created ${s.leftCreatedAt})`,
    `- Right snapshot: ${s.rightSnapshotId} (created ${s.rightCreatedAt})`,
    "- No release label: per-source revisions identify each snapshot.",
    "",
    "## Sources",
    "",
  ];
  for (const row of s.sources) {
    lines.push(
      `- ${row.sourceId}: ${RELATION_LABELS[row.relation]} — left ${row.leftRevision ?? "—"} (${row.leftRevisionStatus ?? "—"}), right ${row.rightRevision ?? "—"} (${row.rightRevisionStatus ?? "—"})`,
    );
  }
  for (const w of s.warnings) {
    lines.push(`- Warning: ${w}`);
  }
  lines.push("", "## Differences", "");
  for (const d of result.differences) {
    const refs = [...d.leftEvidenceIds, ...d.rightEvidenceIds].map((id) => `[${id}]`).join(" ");
    const why = coverageText(d);
    lines.push(`- **${TYPE_LABELS[d.type]}**${why ? ` (${why})` : ""}: ${d.statement}${refs ? ` ${refs}` : ""}`);
  }
  if (result.differences.length === 0) {
    lines.push("- None reported.");
  }
  for (const [label, answer] of [["Left", result.left], ["Right", result.right]] as const) {
    lines.push("", `## ${label} answer (${answer.snapshotId}, ${answer.status})`, "");
    for (const claim of answer.claims) {
      const refs = claim.citationIds.map((id) => `[${id}]`).join(" ");
      lines.push(`- **[${claim.kind}]** ${claim.text}${refs ? ` ${refs}` : ""}`);
    }
    for (const c of answer.citations) {
      lines.push(citationLine(c));
    }
  }
  lines.push("", "## Compared evidence", "");
  for (const c of [...result.evidence.left, ...result.evidence.right]) {
    lines.push(citationLine(c));
  }
  const model = result.model ? `${result.model.provider}/${result.model.name} (${result.model.digest})` : "not used";
  lines.push("", "---", `Left: ${s.leftSnapshotId} · Right: ${s.rightSnapshotId} · Model: ${model}`);
  return lines.join("\n") + "\n";
}

export function buildComparisonJson(result: ComparisonViewModel, exportedAt: string): Record<string, unknown> {
  const citation = (c: CitationViewModel) => ({
    evidence_id: c.evidenceId,
    snapshot_id: c.snapshotId,
    chunk_id: c.chunkId,
    source_id: c.sourceId,
    path: c.path,
    heading_path: c.headingPath,
    revision: c.revision,
    revision_status: c.revisionStatus,
    line_start: c.lineStart,
    line_end: c.lineEnd,
    excerpt: c.excerpt,
    immutable_url: c.upstreamUrl,
    revision_match: c.revisionMatch,
  });
  const answer = (a: ComparisonViewModel["left"]) => ({
    snapshot_id: a.snapshotId,
    status: a.status,
    origin: a.origin,
    claims: a.claims.map((c) => ({ text: c.text, kind: c.kind, evidence_ids: c.citationIds })),
    limitations: a.limitations,
    citations: a.citations.map(citation),
  });
  const s = result.snapshots;
  return {
    question: result.question,
    left_snapshot_id: s.leftSnapshotId,
    right_snapshot_id: s.rightSnapshotId,
    release_label: null,
    sources: s.sources.map((r) => ({
      source_id: r.sourceId,
      relation: r.relation,
      left_revision: r.leftRevision,
      right_revision: r.rightRevision,
      left_revision_status: r.leftRevisionStatus,
      right_revision_status: r.rightRevisionStatus,
    })),
    snapshot_warnings: s.warnings,
    differences: result.differences.map((d) => ({
      type: d.type,
      statement: d.statement,
      left_evidence_ids: d.leftEvidenceIds,
      right_evidence_ids: d.rightEvidenceIds,
      origin: d.origin,
      coverage_reason: d.coverageReason,
      missing_side: d.missingSide,
    })),
    left: answer(result.left),
    right: answer(result.right),
    evidence: { left: result.evidence.left.map(citation), right: result.evidence.right.map(citation) },
    model: result.model,
    origin: result.origin,
    warnings: result.warnings,
    exported_at: exportedAt,
  };
}
