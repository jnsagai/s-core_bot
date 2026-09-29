/**
 * Display models derived from the F005 answer envelope and F004 citation records
 * (data-model.md AnswerViewModel / CitationViewModel). Pure functions; nothing is stored.
 */
import type { CitationRecord } from "../api/citations";

export type ClaimKind = "documented" | "interpretation" | "limitation";

export interface CitationViewModel {
  evidenceId: string;
  chunkId: string;
  snapshotId: string;
  title: string;
  headingPath: string[];
  sourceId: string;
  revision: string;
  revisionStatus: string;
  path: string;
  excerpt: string;
  lineStart: number | null;
  lineEnd: number | null;
  upstreamUrl: string | null;
  revisionMatch: "exact" | "unverified" | "none";
}

export interface AnswerViewModel {
  requestId: string;
  question: string;
  status: string;
  origin: string;
  claims: { text: string; kind: ClaimKind; citationIds: string[] }[];
  limitations: string[];
  citations: CitationViewModel[];
  snapshotId: string;
  model: { provider: string; name: string; digest: string } | null;
  warnings: string[];
}

type Wire = Record<string, unknown>;

const str = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;
const num = (value: unknown): number | null => (typeof value === "number" ? value : null);
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

function titleOf(path: string, headingPath: string[]): string {
  return headingPath[0] ?? path.split("/").pop() ?? path;
}

export function toCitationViewModel(wire: Wire): CitationViewModel {
  const headingPath = list(wire.heading_path).map((h) => str(h));
  const path = str(wire.path);
  const match = str(wire.revision_match, "none");
  return {
    evidenceId: str(wire.evidence_id),
    chunkId: str(wire.chunk_id),
    snapshotId: str(wire.snapshot_id),
    title: titleOf(path, headingPath),
    headingPath,
    sourceId: str(wire.source_id),
    revision: str(wire.revision),
    revisionStatus: str(wire.revision_status),
    path,
    excerpt: str(wire.excerpt),
    lineStart: num(wire.line_start),
    lineEnd: num(wire.line_end),
    upstreamUrl: typeof wire.immutable_url === "string" ? wire.immutable_url : null,
    revisionMatch: match === "exact" || match === "unverified" ? match : "none",
  };
}

export function citationFromRecord(record: CitationRecord): CitationViewModel {
  return {
    evidenceId: "",
    chunkId: record.chunkId,
    snapshotId: record.snapshotId,
    title: titleOf(record.path, record.headingPath),
    headingPath: record.headingPath,
    sourceId: record.sourceId,
    revision: record.revision,
    revisionStatus: record.revisionStatus,
    path: record.path,
    excerpt: record.text,
    lineStart: record.lineStart,
    lineEnd: record.lineEnd,
    upstreamUrl: null,
    revisionMatch: record.revisionStatus === "pinned" ? "none" : "unverified",
  };
}

export function toAnswerViewModel(envelope: Wire): AnswerViewModel {
  const model = envelope.model as Wire | null | undefined;
  return {
    requestId: str(envelope.request_id),
    question: str(envelope.question),
    status: str(envelope.status),
    origin: str(envelope.origin),
    claims: list(envelope.claims).map((raw) => {
      const claim = raw as Wire;
      const kind = str(claim.kind);
      return {
        text: str(claim.text),
        kind: kind === "interpretation" || kind === "limitation" ? kind : "documented",
        citationIds: list(claim.evidence_ids).map((e) => str(e)),
      };
    }),
    limitations: list(envelope.limitations).map((l) => str(l)),
    citations: list(envelope.citations).map((c) => toCitationViewModel(c as Wire)),
    snapshotId: str(envelope.snapshot_id),
    model: model
      ? { provider: str(model.provider), name: str(model.name), digest: str(model.digest) }
      : null,
    warnings: list(envelope.warnings).map((w) => str(w)),
  };
}

/** Plain text of the answer's non-limitation claims, used only as follow-up history content. */
export function answerText(answer: AnswerViewModel): string {
  return answer.claims
    .filter((c) => c.kind !== "limitation")
    .map((c) => c.text)
    .join("\n");
}
