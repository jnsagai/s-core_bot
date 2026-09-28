import { afterEach, describe, expect, it, vi } from "vitest";
import { getCitation } from "../../src/api/citations";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("getCitation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds the path from snapshot and chunk ids and maps the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        snapshot_id: "snap-1",
        chunk_id: "chunk-1",
        source_id: "score-platform",
        revision: "abc123",
        revision_status: "pinned",
        path: "docs/example.rst",
        heading_path: ["Example"],
        line_start: 1,
        line_end: 5,
        kind: "prose",
        text: "Example text.",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await getCitation("snap-1", "chunk-1");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("/api/v1/citations/snap-1/chunk-1");
    expect(result.headingPath).toEqual(["Example"]);
    expect(result.text).toBe("Example text.");
  });
});
