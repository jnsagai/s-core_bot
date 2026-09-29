import { apiFetchJson } from "./client";

export interface SnapshotSummary {
  snapshotId: string;
  state: string;
  active: boolean;
  createdAt: string;
  semantic: string | null;
  semanticStatus: string | null;
  chunks: number | null;
  documents: number | null;
  sources: string[];
  limitations: string[];
}

interface SnapshotSummaryWire {
  snapshot_id: string;
  state: string;
  active: boolean;
  created_at: string;
  semantic: string | null;
  semantic_status: string | null;
  chunks: number | null;
  documents: number | null;
  sources: string[];
  limitations: string[];
}

interface SnapshotsResponseWire {
  active: string | null;
  snapshots: SnapshotSummaryWire[];
}

export interface SnapshotsResult {
  active: string | null;
  snapshots: SnapshotSummary[];
}

function toSnapshotSummary(wire: SnapshotSummaryWire): SnapshotSummary {
  return {
    snapshotId: wire.snapshot_id,
    state: wire.state,
    active: wire.active,
    createdAt: wire.created_at,
    semantic: wire.semantic,
    semanticStatus: wire.semantic_status,
    chunks: wire.chunks,
    documents: wire.documents,
    sources: wire.sources,
    limitations: wire.limitations,
  };
}

export async function getSnapshots(): Promise<SnapshotsResult> {
  const wire = await apiFetchJson<SnapshotsResponseWire>("/api/v1/snapshots");
  return { active: wire.active, snapshots: wire.snapshots.map(toSnapshotSummary) };
}

export interface SourceSummary {
  sourceId: string;
  kind: string;
  revision: string | null;
  revisionStatus: string;
  required: boolean;
  status: string;
  licenseReview: string[];
}

interface SourceSummaryWire {
  source_id: string;
  kind: string;
  revision: string | null;
  revision_status: string;
  required: boolean;
  status: string;
  license_review: string[];
}

export async function getSources(snapshotId?: string): Promise<SourceSummary[]> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  const wire = await apiFetchJson<{ sources: SourceSummaryWire[] }>(
    `/api/v1/sources${suffix}` as `/api/v1/${string}`,
  );
  return wire.sources.map((s) => ({
    sourceId: s.source_id,
    kind: s.kind,
    revision: s.revision,
    revisionStatus: s.revision_status,
    required: s.required,
    status: s.status,
    licenseReview: s.license_review,
  }));
}
