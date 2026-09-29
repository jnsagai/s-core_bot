/**
 * Display models for a comparison result (F007 data-model.md ComparisonResult). Pure functions;
 * results live only in component memory, like chat turns.
 */
import { toAnswerViewModel, toCitationViewModel, type AnswerViewModel, type CitationViewModel } from "../answer/model";

export type DifferenceType = "changed" | "unchanged" | "conflicting" | "not_established";

export interface DifferenceViewModel {
  type: DifferenceType;
  statement: string;
  leftEvidenceIds: string[];
  rightEvidenceIds: string[];
  origin: string;
  coverageReason: string | null;
  missingSide: "left" | "right" | "both" | null;
}

export interface SourceRelationViewModel {
  sourceId: string;
  relation: "same" | "different" | "left_only" | "right_only";
  leftRevision: string | null;
  rightRevision: string | null;
  leftRevisionStatus: string | null;
  rightRevisionStatus: string | null;
}

export interface SnapshotDiffViewModel {
  leftSnapshotId: string;
  rightSnapshotId: string;
  leftCreatedAt: string;
  rightCreatedAt: string;
  sources: SourceRelationViewModel[];
  processing: { field: string; left: string | null; right: string | null }[];
  warnings: string[];
}

export interface ComparisonViewModel {
  requestId: string;
  question: string;
  left: AnswerViewModel;
  right: AnswerViewModel;
  differences: DifferenceViewModel[];
  evidence: { left: CitationViewModel[]; right: CitationViewModel[] };
  snapshots: SnapshotDiffViewModel;
  model: { provider: string; name: string; digest: string } | null;
  origin: string;
  warnings: string[];
}

type Wire = Record<string, unknown>;
const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : fallback);
const opt = (v: unknown): string | null => (typeof v === "string" ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const TYPES: DifferenceType[] = ["changed", "unchanged", "conflicting", "not_established"];
const RELATIONS = ["same", "different", "left_only", "right_only"] as const;

export function toSnapshotDiffViewModel(wire: Wire): SnapshotDiffViewModel {
  return {
    leftSnapshotId: str(wire.left_snapshot_id),
    rightSnapshotId: str(wire.right_snapshot_id),
    leftCreatedAt: str(wire.left_created_at),
    rightCreatedAt: str(wire.right_created_at),
    sources: list(wire.sources).map((raw) => {
      const row = raw as Wire;
      const relation = str(row.relation);
      return {
        sourceId: str(row.source_id),
        relation: (RELATIONS as readonly string[]).includes(relation)
          ? (relation as SourceRelationViewModel["relation"])
          : "different",
        leftRevision: opt(row.left_revision),
        rightRevision: opt(row.right_revision),
        leftRevisionStatus: opt(row.left_revision_status),
        rightRevisionStatus: opt(row.right_revision_status),
      };
    }),
    processing: list(wire.processing).map((raw) => {
      const p = raw as Wire;
      return { field: str(p.field), left: opt(p.left), right: opt(p.right) };
    }),
    warnings: list(wire.warnings).map((w) => str(w)),
  };
}

export function toComparisonViewModel(wire: Wire): ComparisonViewModel {
  const evidence = (wire.evidence ?? {}) as Wire;
  const model = wire.model as Wire | null | undefined;
  return {
    requestId: str(wire.request_id),
    question: str(wire.question),
    left: toAnswerViewModel((wire.left ?? {}) as Wire),
    right: toAnswerViewModel((wire.right ?? {}) as Wire),
    differences: list(wire.differences).map((raw) => {
      const d = raw as Wire;
      const type = str(d.type);
      const missing = str(d.missing_side);
      return {
        type: (TYPES as string[]).includes(type) ? (type as DifferenceType) : "not_established",
        statement: str(d.statement),
        leftEvidenceIds: list(d.left_evidence_ids).map((e) => str(e)),
        rightEvidenceIds: list(d.right_evidence_ids).map((e) => str(e)),
        origin: str(d.origin),
        coverageReason: opt(d.coverage_reason),
        missingSide: missing === "left" || missing === "right" || missing === "both" ? missing : null,
      };
    }),
    evidence: {
      left: list(evidence.left).map((c) => toCitationViewModel(c as Wire)),
      right: list(evidence.right).map((c) => toCitationViewModel(c as Wire)),
    },
    snapshots: toSnapshotDiffViewModel((wire.snapshots ?? {}) as Wire),
    model: model ? { provider: str(model.provider), name: str(model.name), digest: str(model.digest) } : null,
    origin: str(wire.origin),
    warnings: list(wire.warnings).map((w) => str(w)),
  };
}

export const TYPE_LABELS: Record<DifferenceType, string> = {
  changed: "Changed",
  unchanged: "Unchanged",
  conflicting: "Conflicting (neither side is chosen)",
  not_established: "Not established",
};

const REASON_TEXT: Record<string, string> = {
  source_absent: "the source is not in the {side} snapshot",
  source_failed: "the source failed to sync in the {side} snapshot",
  source_partial: "the source is only partly covered in the {side} snapshot",
  record_not_found: "the record was not found in the {side} snapshot's records",
  record_without_excerpt: "the record has no excerpt in the {side} snapshot",
  not_retrieved: "it was not found in the {side} snapshot's retrieved evidence",
  no_evidence: "the {side} snapshot returned no evidence for this question",
};

/** Why a difference is not established; never phrased as removal or addition. */
export function coverageText(d: DifferenceViewModel): string | null {
  if (d.type !== "not_established" || !d.coverageReason) {
    return null;
  }
  const side = d.missingSide === "both" ? "either" : (d.missingSide ?? "other");
  return (REASON_TEXT[d.coverageReason] ?? d.coverageReason).replace("{side}", side);
}

export const RELATION_LABELS: Record<SourceRelationViewModel["relation"], string> = {
  same: "same revision",
  different: "different revision",
  left_only: "only in the left snapshot",
  right_only: "only in the right snapshot",
};
