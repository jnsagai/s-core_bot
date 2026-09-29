import { afterEach, describe, expect, it, vi } from "vitest";
import { compare, getSnapshotDiff, streamCompare } from "../../src/api/compare";
import { BASELINE, COMPARISON, SNAPSHOT, installFetch, json, sse } from "../helpers/fetch";

afterEach(() => vi.unstubAllGlobals());

describe("compare API (T022)", () => {
  it("posts both snapshot IDs and never sends history", async () => {
    const mock = installFetch({ "POST /api/v1/compare": () => json(COMPARISON) });
    const result = await compare({ question: "q", leftSnapshotId: BASELINE, rightSnapshotId: SNAPSHOT });
    expect(result.request_id).toBe("cmp-1");
    const body = JSON.parse(String(mock.calls[0].init!.body));
    expect(body).toEqual({ question: "q", left_snapshot_id: BASELINE, right_snapshot_id: SNAPSHOT });
  });

  it("streams progress with sides and one comparison event", async () => {
    const mock = installFetch({
      "POST /api/v1/compare": () =>
        sse([
          { event: "progress", data: { stage: "searching", side: "left" } },
          { event: "progress", data: { stage: "comparing" } },
          { event: "comparison", data: COMPARISON },
          { event: "done", data: {} },
        ]),
    });
    const events = [];
    for await (const e of streamCompare({ question: "q", leftSnapshotId: BASELINE, rightSnapshotId: SNAPSHOT })) {
      events.push(e);
    }
    expect(events.map((e) => e.event)).toEqual(["progress", "progress", "comparison", "done"]);
    expect(events[0].data).toEqual({ stage: "searching", side: "left" });
    const headers = new Headers(mock.calls[0].init!.headers);
    expect(headers.get("accept")).toBe("text/event-stream");
  });

  it("requests the snapshot diff with encoded query parameters", async () => {
    const mock = installFetch({ "GET /api/v1/snapshots/diff": () => json(COMPARISON.snapshots) });
    const diff = await getSnapshotDiff(BASELINE, SNAPSHOT);
    expect(diff.release_label).toBeNull();
    expect(mock.calls[0].url).toBe(`/api/v1/snapshots/diff?left=${BASELINE}&right=${SNAPSHOT}`);
  });
});
