import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../src/App";
import { buildComparisonJson, buildComparisonMarkdown } from "../../src/comparison/export";
import { coverageText, toComparisonViewModel } from "../../src/comparison/model";
import {
  BASELINE,
  COMPARISON,
  SNAPSHOT,
  compareRoutes,
  installFetch,
  json,
  sse,
} from "../helpers/fetch";

afterEach(() => vi.unstubAllGlobals());

const STREAM = () =>
  sse([
    { event: "progress", data: { stage: "searching", side: "left" } },
    { event: "progress", data: { stage: "generating", side: "right" } },
    { event: "progress", data: { stage: "comparing" } },
    { event: "comparison", data: COMPARISON },
    { event: "done", data: {} },
  ]);

async function openCompare(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
  await user.click(screen.getByRole("tab", { name: "Compare" }));
}

describe("Compare tab (T024, T025, FR-018)", () => {
  it("defaults to active vs the other snapshot, streams, and labels both sides", async () => {
    const mock = installFetch(compareRoutes({ "POST /api/v1/compare": STREAM }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    expect(screen.getByLabelText("Left snapshot")).toHaveValue(BASELINE);
    expect(screen.getByLabelText("Right snapshot")).toHaveValue(SNAPSHOT);
    await user.type(screen.getByLabelText("Question to compare"), "How are inspections performed?");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Differences" })).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: `Left: ${BASELINE}` })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: `Right: ${SNAPSHOT}` })).toBeInTheDocument();
    expect(screen.getByText(/The left requires two reviewers/)).toBeInTheDocument();
    expect(screen.getByText(/not found in the left snapshot's retrieved evidence/)).toBeInTheDocument();
    expect(screen.getByText("No release label: per-source revisions identify each snapshot.")).toBeInTheDocument();
    expect(screen.getByText("only in the right snapshot")).toBeInTheDocument();
    const body = JSON.parse(String(mock.calls.find((c) => c.url === "/api/v1/compare")!.init!.body));
    expect(body).toEqual({ question: "How are inspections performed?", left_snapshot_id: BASELINE, right_snapshot_id: SNAPSHOT });
    expect(mock.calls.some((c) => c.url === "/api/v1/chat")).toBe(false);
  });

  it("opens the left excerpt from an L button and the right excerpt from an R button", async () => {
    installFetch(compareRoutes({ "POST /api/v1/compare": STREAM }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    await user.type(screen.getByLabelText("Question to compare"), "q");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => screen.getByRole("heading", { name: "Differences" }));
    await user.click(screen.getByRole("button", { name: /Open left evidence L1/ }));
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/two reviewers \(left\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/82bca166065/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: /Open right evidence R1/ }));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/three reviewers \(right\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/66321fe6bd13/)).toBeInTheDocument();
  });

  it("blocks the same snapshot on both sides", async () => {
    const mock = installFetch(compareRoutes({ "POST /api/v1/compare": STREAM }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    await user.selectOptions(screen.getByLabelText("Left snapshot"), SNAPSHOT);
    await user.type(screen.getByLabelText("Question to compare"), "q");
    expect(screen.getByText("Pick two different snapshots to compare.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();
    expect(mock.calls.some((c) => c.url === "/api/v1/compare")).toBe(false);
  });

  it("explains how to get a second snapshot when only one exists", async () => {
    installFetch(compareRoutes({
      "GET /api/v1/snapshots": () => json({ active: SNAPSHOT, snapshots: [COMPARISON_SNAPSHOT] }),
    }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    expect(screen.getByText(/Comparison needs two documentation snapshots/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();
  });

  it("stop aborts the request and offers retry", async () => {
    let signal: AbortSignal | undefined;
    installFetch(compareRoutes({
      "POST /api/v1/compare": (init) => {
        signal = init?.signal ?? undefined;
        return sse([{ event: "progress", data: { stage: "searching", side: "left" } }], { hold: true });
      },
    }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    await user.type(screen.getByLabelText("Question to compare"), "q");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(screen.getByText("Left snapshot: Searching the documentation", { selector: ".status" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(signal?.aborted).toBe(true);
    expect(screen.getByText(/Stopped\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  });

  it("shows a typed error with retry and no automatic retry", async () => {
    const mock = installFetch(compareRoutes({
      "POST /api/v1/compare": () =>
        sse([{ event: "error", data: { error: { code: "CHAT_BUSY", message: "busy" } } }, { event: "done", data: {} }]),
    }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    await user.type(screen.getByLabelText("Question to compare"), "q");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Another answer or comparison is running"));
    expect(mock.calls.filter((c) => c.url === "/api/v1/compare")).toHaveLength(1);
  });

  it("downloads Markdown and JSON exports via Blobs", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", { ...URL, createObjectURL: (b: Blob) => (created.push(b), "blob:x"), revokeObjectURL: () => undefined });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    installFetch(compareRoutes({ "POST /api/v1/compare": STREAM }));
    const user = userEvent.setup();
    render(<App />);
    await openCompare(user);
    expect(screen.queryByRole("button", { name: "Export JSON" })).toBeNull();
    await user.type(screen.getByLabelText("Question to compare"), "q");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => screen.getByRole("heading", { name: "Differences" }));
    const group = screen.getByRole("group", { name: "Export this comparison" });
    await user.click(within(group).getByRole("button", { name: "Export Markdown" }));
    await user.click(within(group).getByRole("button", { name: "Export JSON" }));
    expect(created.map((b) => b.type)).toEqual(["text/markdown", "application/json"]);
    click.mockRestore();
  });
});

const COMPARISON_SNAPSHOT = {
  snapshot_id: SNAPSHOT, state: "active", active: true, created_at: "2026-09-28T14:05:48Z",
  semantic: "present", semantic_status: "enabled", chunks: 1, documents: 1, sources: [], limitations: [],
};

describe("Comparison export content (T023, FR-019, SC-003)", () => {
  const result = toComparisonViewModel(COMPARISON);

  it("keeps both snapshot identities, revisions, differences and the model", () => {
    const md = buildComparisonMarkdown(result);
    expect(md).toContain(`Left snapshot: ${BASELINE}`);
    expect(md).toContain(`Right snapshot: ${SNAPSHOT}`);
    expect(md).toContain("82bca166065990e52b871de47c87668b6a3d5f49");
    expect(md).toContain("66321fe6bd131eae58fbd6395b0f0b92d63e00f5");
    expect(md).toContain("**Changed**: The left requires two reviewers; the right requires three. [L1] [R1]");
    expect(md).toContain("No release label");
    expect(md).toContain("ollama/qwen3:4b-instruct");
    const data = buildComparisonJson(result, "2026-09-29T08:00:00.000Z");
    expect(data).toMatchObject({ left_snapshot_id: BASELINE, right_snapshot_id: SNAPSHOT, release_label: null });
    expect((data.left as { snapshot_id: string }).snapshot_id).toBe(BASELINE);
    expect((data.evidence as { left: { snapshot_id: string }[] }).left[0].snapshot_id).toBe(BASELINE);
    expect((data.differences as unknown[]).length).toBe(2);
  });

  it("contains no absolute machine path or credential-shaped string", () => {
    const text = buildComparisonMarkdown(result) + JSON.stringify(buildComparisonJson(result, "t"));
    expect(text).not.toMatch(/\/home\/|\/Users\/|[A-Z]:\\\\|\/tmp\/|data\/snapshots/);
    expect(text).not.toMatch(/(api[_-]?key|token|password|secret)\s*[:=]/i);
  });

  it("phrases coverage as not found, never as removed", () => {
    const text = result.differences.map((d) => coverageText(d) ?? "").join(" ");
    expect(text).toContain("not found in the left snapshot's retrieved evidence");
    expect(text).not.toMatch(/remov|delet|added|no longer/i);
  });
});
