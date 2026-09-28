import { afterEach, describe, expect, it, vi } from "vitest";
import { search } from "../../src/api/search";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("search", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to /api/v1/search and never calls chat", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        snapshot_id: "snap-1",
        status: "ok",
        mode: "hybrid",
        degraded: null,
        semantic_status: "enabled",
        exact_matches: [],
        results: [
          {
            rank: 1,
            chunk_id: "chunk-1",
            snapshot_id: "snap-1",
            source_id: "score-platform",
            revision: "abc123",
            revision_status: "pinned",
            path: "docs/example.rst",
            heading_path: ["Example"],
            line_start: 1,
            line_end: 5,
            kind: "prose",
            excerpt: "Example text.",
            truncated: false,
            matched_by: ["keyword"],
            ranking_value: 0.5,
          },
        ],
        warnings: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await search("how do I build docs?", { snapshotId: "snap-1" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("/api/v1/search");
    expect(result.results[0].chunkId).toBe("chunk-1");
    expect(result.results[0].headingPath).toEqual(["Example"]);
  });
});
