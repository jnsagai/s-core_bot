import { afterEach, describe, expect, it, vi } from "vitest";
import { getSnapshots, getSources } from "../../src/api/snapshots";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("getSnapshots", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("maps snapshot summaries to camelCase", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          active: "snap-1",
          snapshots: [
            {
              snapshot_id: "snap-1",
              state: "active",
              active: true,
              created_at: "2026-09-28T00:00:00Z",
              semantic: "enabled",
              semantic_status: "enabled",
              chunks: 100,
              documents: 10,
              sources: ["score-platform"],
              limitations: [],
            },
          ],
        }),
      ),
    );

    const result = await getSnapshots();
    expect(result.active).toBe("snap-1");
    expect(result.snapshots[0].snapshotId).toBe("snap-1");
    expect(result.snapshots[0].createdAt).toBe("2026-09-28T00:00:00Z");
  });
});

describe("getSources", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("includes the snapshot_id query param when provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { sources: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getSources("snap-1");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("/api/v1/sources?snapshot_id=snap-1");
  });
});
