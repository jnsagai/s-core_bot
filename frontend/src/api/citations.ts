import { apiFetchJson } from "./client";

export interface CitationRecord {
  snapshotId: string;
  chunkId: string;
  sourceId: string;
  revision: string;
  revisionStatus: string;
  path: string;
  headingPath: string[];
  lineStart: number | null;
  lineEnd: number | null;
  kind: string;
  text: string;
}

interface CitationRecordWire {
  snapshot_id: string;
  chunk_id: string;
  source_id: string;
  revision: string;
  revision_status: string;
  path: string;
  heading_path: string[];
  line_start: number | null;
  line_end: number | null;
  kind: string;
  text: string;
}

export async function getCitation(snapshotId: string, chunkId: string): Promise<CitationRecord> {
  const path = `/api/v1/citations/${encodeURIComponent(snapshotId)}/${encodeURIComponent(
    chunkId,
  )}` as `/api/v1/${string}`;
  const wire = await apiFetchJson<CitationRecordWire>(path);
  return {
    snapshotId: wire.snapshot_id,
    chunkId: wire.chunk_id,
    sourceId: wire.source_id,
    revision: wire.revision,
    revisionStatus: wire.revision_status,
    path: wire.path,
    headingPath: wire.heading_path,
    lineStart: wire.line_start,
    lineEnd: wire.line_end,
    kind: wire.kind,
    text: wire.text,
  };
}
