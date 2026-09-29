import { useState } from "react";
import { getCitation } from "../api/citations";
import { ApiError } from "../api/client";
import { search, type SearchResult } from "../api/search";
import { citationFromRecord, type CitationViewModel } from "../answer/model";
import { EvidencePanel } from "./EvidencePanel";

const KINDS = ["prose", "need", "table", "code", "literal", "diagram"];

/** Direct evidence search (FR-018): never calls the answer model. */
export function SearchPanel({
  snapshotId,
  sources,
  announce,
}: {
  snapshotId: string | null;
  sources: string[];
  announce: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [kind, setKind] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openCitation, setOpenCitation] = useState<CitationViewModel | null>(null);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    announce("Searching the documentation");
    try {
      const found = await search(query, {
        snapshotId,
        sources: source ? [source] : undefined,
        kinds: kind ? [kind] : undefined,
      });
      setResult(found);
      announce(found.results.length ? `${found.results.length} results` : "No results");
    } catch (caught) {
      setResult(null);
      setError(caught instanceof ApiError ? `${caught.message} (${caught.code})` : "Search failed.");
      announce("Search failed");
    } finally {
      setBusy(false);
    }
  }

  async function open(snapshot: string, chunkId: string) {
    try {
      setOpenCitation(citationFromRecord(await getCitation(snapshot, chunkId)));
    } catch {
      setError("The excerpt could not be loaded.");
    }
  }

  return (
    <section aria-labelledby="search-heading">
      <h2 id="search-heading">Search the documentation</h2>
      <form onSubmit={run} className="search-form">
        <label htmlFor="search-query">Search terms or requirement ID</label>
        <input id="search-query" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label htmlFor="search-source">Source</label>
        <select id="search-source" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label htmlFor="search-kind">Content kind</label>
        <select id="search-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All kinds</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy || !query.trim()}>
          Search
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result?.degraded && result.degraded.reason !== "lexical_requested" && (
        <p className="notice">
          Keyword results only: semantic search is unavailable ({result.degraded.reason}).
          {result.degraded.guidance.map((g) => ` ${g}`)}
        </p>
      )}
      {result && result.exactMatches.length > 0 && (
        <div className="exact">
          <h3>Exact requirement matches</h3>
          <ul>
            {result.exactMatches.map((m) => (
              <li key={m.key}>
                <code>{m.needId}</code> — {m.title} <span className="muted">({m.sourceId}, {m.revisionStatus})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result && result.status === "no_results" && <p>No results.</p>}
      {result && result.results.length > 0 && (
        <ol className="results">
          {result.results.map((r) => (
            <li key={r.chunkId}>
              <p>
                <strong>{r.headingPath.join(" › ") || r.path}</strong>{" "}
                <span className="muted">
                  {r.sourceId} · {r.path}
                  {r.lineStart !== null ? `:${r.lineStart}` : ""} · {r.kind} · matched by {r.matchedBy.join(", ")}
                </span>
              </p>
              <p className="excerpt-text">{r.excerpt}</p>
              <button type="button" onClick={() => void open(r.snapshotId, r.chunkId)}>
                Open excerpt
              </button>
            </li>
          ))}
        </ol>
      )}
      {openCitation && <EvidencePanel citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  );
}
