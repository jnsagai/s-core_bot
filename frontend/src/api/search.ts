import { apiFetchJson } from "./client";

export interface EvidenceResult {
  rank: number;
  chunkId: string;
  snapshotId: string;
  sourceId: string;
  revision: string;
  revisionStatus: string;
  path: string;
  headingPath: string[];
  lineStart: number | null;
  lineEnd: number | null;
  kind: string;
  excerpt: string;
  truncated: boolean;
  matchedBy: string[];
  rankingValue: number | null;
}

export interface EntitySummary {
  key: string;
  needId: string;
  match: "exact" | "alias";
  sourceId: string;
  revisionStatus: string;
  title: string;
}

export interface SearchResult {
  snapshotId: string;
  status: "ok" | "no_results";
  mode: "hybrid" | "lexical";
  degraded: { reason: string; detail: string; guidance: string[] } | null;
  semanticStatus: string;
  exactMatches: EntitySummary[];
  results: EvidenceResult[];
  warnings: string[];
}

interface SearchResponseWire {
  snapshot_id: string;
  status: "ok" | "no_results";
  mode: "hybrid" | "lexical";
  degraded: { reason: string; detail: string; guidance: string[] } | null;
  semantic_status: string;
  exact_matches: Array<{
    key: string;
    need_id: string;
    match: "exact" | "alias";
    source_id: string;
    revision_status: string;
    title: string;
  }>;
  results: Array<{
    rank: number;
    chunk_id: string;
    snapshot_id: string;
    source_id: string;
    revision: string;
    revision_status: string;
    path: string;
    heading_path: string[];
    line_start: number | null;
    line_end: number | null;
    kind: string;
    excerpt: string;
    truncated: boolean;
    matched_by: string[];
    ranking_value: number | null;
  }>;
  warnings: string[];
}

export interface SearchOptions {
  snapshotId?: string | null;
  limit?: number;
  sources?: string[];
  kinds?: string[];
}

export async function search(query: string, options: SearchOptions = {}): Promise<SearchResult> {
  const wire = await apiFetchJson<SearchResponseWire>("/api/v1/search", {
    method: "POST",
    body: {
      query,
      snapshot_id: options.snapshotId ?? null,
      limit: options.limit,
      sources: options.sources,
      kinds: options.kinds,
    },
  });
  return {
    snapshotId: wire.snapshot_id,
    status: wire.status,
    mode: wire.mode,
    degraded: wire.degraded,
    semanticStatus: wire.semantic_status,
    exactMatches: wire.exact_matches.map((m) => ({
      key: m.key,
      needId: m.need_id,
      match: m.match,
      sourceId: m.source_id,
      revisionStatus: m.revision_status,
      title: m.title,
    })),
    results: wire.results.map((r) => ({
      rank: r.rank,
      chunkId: r.chunk_id,
      snapshotId: r.snapshot_id,
      sourceId: r.source_id,
      revision: r.revision,
      revisionStatus: r.revision_status,
      path: r.path,
      headingPath: r.heading_path,
      lineStart: r.line_start,
      lineEnd: r.line_end,
      kind: r.kind,
      excerpt: r.excerpt,
      truncated: r.truncated,
      matchedBy: r.matched_by,
      rankingValue: r.ranking_value,
    })),
    warnings: wire.warnings,
  };
}
