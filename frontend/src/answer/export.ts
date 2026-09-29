import type { AnswerViewModel } from "./model";

/** Markdown/JSON export of a validated answer (FR-016, contracts/ui-contract.md §4). Only envelope
 * fields are used, so no machine path, environment value or credential can appear. */
export function buildMarkdownExport(answer: AnswerViewModel): string {
  const lines = [`# Question`, "", answer.question, "", `# Answer (${answer.status})`, ""];
  for (const claim of answer.claims) {
    const refs = claim.citationIds.map((id) => `[${id}]`).join(" ");
    lines.push(`- **[${claim.kind}]** ${claim.text}${refs ? ` ${refs}` : ""}`);
  }
  if (answer.citations.length > 0) {
    lines.push("", "## Citations", "");
    for (const c of answer.citations) {
      const section = c.headingPath.length ? ` § ${c.headingPath.join(" › ")}` : "";
      lines.push(
        `- **${c.evidenceId}** — ${c.sourceId}:${c.path}${section} (rev ${c.revision.slice(0, 12)}) — ${c.excerpt.replace(/\s+/g, " ")}`,
      );
      if (c.upstreamUrl) {
        lines.push(`  ${c.upstreamUrl} (${c.revisionMatch})`);
      }
    }
  }
  const model = answer.model ? `${answer.model.provider}/${answer.model.name} (${answer.model.digest})` : "not used";
  lines.push("", "---", `Snapshot: ${answer.snapshotId} · Model: ${model}`);
  return lines.join("\n") + "\n";
}

export function buildJsonExport(answer: AnswerViewModel, exportedAt: string): Record<string, unknown> {
  return {
    question: answer.question,
    status: answer.status,
    origin: answer.origin,
    claims: answer.claims.map((c) => ({ text: c.text, kind: c.kind, evidence_ids: c.citationIds })),
    limitations: answer.limitations,
    citations: answer.citations.map((c) => ({
      evidence_id: c.evidenceId,
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
    })),
    snapshot_id: answer.snapshotId,
    model: answer.model,
    exported_at: exportedAt,
  };
}
