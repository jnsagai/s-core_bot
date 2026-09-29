import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../src/App";
import { buildJsonExport, buildMarkdownExport } from "../../src/answer/export";
import { toAnswerViewModel } from "../../src/answer/model";
import { ENVELOPE, SNAPSHOT, SNAPSHOTS, baseRoutes, installFetch, json, sse } from "../helpers/fetch";

afterEach(() => vi.unstubAllGlobals());

const SEARCH = {
  snapshot_id: SNAPSHOT, status: "ok", mode: "lexical",
  degraded: { reason: "embedding_runtime_unavailable", detail: "down", guidance: [] },
  semantic_status: "unverified",
  exact_matches: [{ key: "score-platform:feat_req__com__interfaces", need_id: "feat_req__com__interfaces", match: "exact", source_id: "score-platform", revision_status: "pinned", title: "Communication Interfaces" }],
  results: [{
    rank: 1, chunk_id: "b".repeat(64), snapshot_id: SNAPSHOT, source_id: "score-platform", revision: "e2373d8",
    revision_status: "pinned", path: "docs/features/communication/requirements/index.rst",
    origin_path: "docs/features/communication/requirements/index.rst", heading_path: ["Communication"],
    line_start: 67, line_end: 82, kind: "need", entity_keys: [], excerpt: "Communication Interfaces <b>x</b>",
    truncated: false, matched_by: ["exact", "keyword"], ranking_value: null,
  }],
  warnings: [],
};
const CITATION = {
  snapshot_id: SNAPSHOT, chunk_id: "b".repeat(64), source_id: "score-platform", revision: "e2373d8",
  revision_status: "pinned", path: "docs/features/communication/requirements/index.rst", origin_path: "x",
  heading_path: ["Communication"], line_start: 67, line_end: 82, kind: "need", entity_keys: [],
  text: "Communication Interfaces full text", continuation: null,
};

describe("SearchPanel (T017, FR-018)", () => {
  it("searches with filters, shows degraded mode, exact matches, provenance; never calls chat", async () => {
    const mock = installFetch(baseRoutes({
      "POST /api/v1/search": () => json(SEARCH),
      [`GET /api/v1/citations/${SNAPSHOT}/${"b".repeat(64)}`]: () => json(CITATION),
    }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await user.click(screen.getByRole("tab", { name: "Search" }));
    await user.type(screen.getByLabelText("Search terms or requirement ID"), "feat_req__com__interfaces");
    await user.selectOptions(screen.getByLabelText("Source"), "score-platform");
    await user.selectOptions(screen.getByLabelText("Content kind"), "need");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/Keyword results only/)).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Exact requirement matches" })).toBeInTheDocument();
    expect(screen.getByText(/matched by exact, keyword/)).toBeInTheDocument();
    expect(screen.getByText("Communication Interfaces <b>x</b>")).toBeInTheDocument(); // text, not HTML
    const body = JSON.parse(String(mock.calls.find((c) => c.url === "/api/v1/search")!.init!.body));
    expect(body).toMatchObject({ query: "feat_req__com__interfaces", snapshot_id: SNAPSHOT, sources: ["score-platform"], kinds: ["need"] });
    await user.click(screen.getByRole("button", { name: "Open excerpt" }));
    expect(within(screen.getByRole("dialog")).getByText(/full text/)).toBeInTheDocument();
    expect(mock.calls.some((c) => c.url === "/api/v1/chat")).toBe(false);
  });
});

async function answerOnce(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
  await user.type(screen.getByLabelText("Your question"), "How are inspections performed?");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
}

const CHAT = () => sse([{ event: "answer", data: ENVELOPE }, { event: "done", data: {} }]);

describe("SnapshotSelector (T024, FR-017)", () => {
  it("applies immediately with an empty conversation", async () => {
    installFetch(baseRoutes());
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Documentation snapshot"), SNAPSHOTS.snapshots[1].snapshot_id);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText(`Snapshot: ${SNAPSHOTS.snapshots[1].snapshot_id}`)).toBeInTheDocument();
  });

  it("asks for confirmation with turns; cancel keeps, confirm clears and switches", async () => {
    installFetch(baseRoutes({ "POST /api/v1/chat": CHAT }));
    const user = userEvent.setup();
    render(<App />);
    await answerOnce(user);
    const other = SNAPSHOTS.snapshots[1].snapshot_id;
    await user.selectOptions(screen.getByLabelText("Documentation snapshot"), other);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Keep current snapshot" }));
    expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument();
    expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Documentation snapshot"), other);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Switch and clear" }));
    expect(screen.getByText(`Snapshot: ${other}`)).toBeInTheDocument();
    expect(screen.queryByText("Answered from the cited sources")).toBeNull();
  });
});

describe("New conversation (T025, US3 AS1)", () => {
  it("clears turns so no prior turn is sent as history", async () => {
    const mock = installFetch(baseRoutes({ "POST /api/v1/chat": CHAT }));
    const user = userEvent.setup();
    render(<App />);
    await answerOnce(user);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByText("Answered from the cited sources")).toBeNull();
    await answerOnce(user);
    const bodies = mock.calls.filter((c) => c.url === "/api/v1/chat").map((c) => JSON.parse(String(c.init!.body)));
    expect(bodies[1].history).toEqual([]);
  });

  it("a remount (reload) starts empty", async () => {
    installFetch(baseRoutes({ "POST /api/v1/chat": CHAT }));
    const user = userEvent.setup();
    const { unmount } = render(<App />);
    await answerOnce(user);
    unmount();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    expect(screen.queryByText("Answered from the cited sources")).toBeNull();
  });
});

describe("Export (T026, FR-016, SC-005)", () => {
  const answer = toAnswerViewModel(ENVELOPE);

  it("Markdown and JSON carry question, claims, citations, snapshot and model identity", () => {
    const md = buildMarkdownExport(answer);
    expect(md).toContain("How are inspections performed?");
    expect(md).toContain("**[documented]** Inspections are formal reviews supported by a checklist. [E1]");
    expect(md).toContain("score-process:process/general_concepts/score_review_concept.rst");
    expect(md).toContain(`Snapshot: ${SNAPSHOT}`);
    expect(md).toContain("ollama/qwen3:4b-instruct (0edcdef3");
    const data = buildJsonExport(answer, "2026-09-29T08:00:00.000Z");
    expect(data).toMatchObject({ question: answer.question, status: "answered", snapshot_id: SNAPSHOT });
    expect((data.citations as unknown[]).length).toBe(1);
    expect((data.model as { digest: string }).digest).toMatch(/^0edcdef3/);
  });

  it("contains no absolute machine path or credential-shaped string", () => {
    const text = buildMarkdownExport(answer) + JSON.stringify(buildJsonExport(answer, "t"));
    expect(text).not.toMatch(/\/home\/|\/Users\/|[A-Z]:\\\\|\/tmp\/|data\/snapshots/);
    expect(text).not.toMatch(/(api[_-]?key|token|password|secret)\s*[:=]/i);
  });

  it("is offered only for a completed answer and downloads via a Blob", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", { ...URL, createObjectURL: (b: Blob) => (created.push(b), "blob:x"), revokeObjectURL: () => undefined });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    installFetch(baseRoutes({ "POST /api/v1/chat": CHAT }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Export Markdown" })).toBeNull();
    await answerOnce(user);
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(created).toHaveLength(1);
    expect(created[0].type).toBe("application/json");
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});
