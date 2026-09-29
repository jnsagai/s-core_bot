import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../src/App";
import { toAnswerViewModel } from "../../src/answer/model";
import { AnswerView } from "../../src/components/AnswerView";
import { EvidencePanel } from "../../src/components/EvidencePanel";
import { LiveRegion } from "../../src/components/LiveRegion";
import { StatusBadge } from "../../src/components/StatusBadge";
import { useAnnouncer } from "../../src/state/announcer";
import { CAPABILITIES, ENVELOPE, SNAPSHOT, baseRoutes, installFetch, json, sse } from "../helpers/fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

const STREAM = [
  { event: "progress", data: { stage: "queued", position: 1 } },
  { event: "progress", data: { stage: "searching" } },
  { event: "progress", data: { stage: "generating" } },
  { event: "progress", data: { stage: "validating" } },
  { event: "answer", data: ENVELOPE },
  { event: "done", data: {} },
];

async function ask(user: ReturnType<typeof userEvent.setup>, question: string) {
  await user.type(screen.getByLabelText("Your question"), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
}

describe("StatusBadge and LiveRegion (T014, FR-004)", () => {
  it("labels every state and the queue position", () => {
    const { rerender } = render(<StatusBadge status="queued" position={2} />);
    expect(screen.getByText("Queued (position 2)")).toBeInTheDocument();
    for (const [status, text] of [
      ["searching", "Searching the documentation"],
      ["generating", "Generating an answer"],
      ["validating", "Checking the answer against its sources"],
      ["failed", "Failed"],
      ["cancelled", "Stopped"],
    ] as const) {
      rerender(<StatusBadge status={status} />);
      expect(screen.getByText(text)).toBeInTheDocument();
    }
  });

  it("announces each distinct message once (T030)", () => {
    const seen: string[] = [];
    function Harness({ messages }: { messages: string[] }) {
      const [message, announce] = useAnnouncer();
      for (const m of messages) announce(m);
      seen.push(message);
      return <LiveRegion message={message} />;
    }
    const { rerender } = render(<Harness messages={["Searching"]} />);
    rerender(<Harness messages={["Searching", "Searching"]} />);
    rerender(<Harness messages={["Generating"]} />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Generating");
    expect(new Set(seen.filter(Boolean))).toEqual(new Set(["Searching", "Generating"]));
  });
});

describe("AnswerView and EvidencePanel (T015, FR-007, FR-008)", () => {
  it("groups claims by kind, labels interpretation, lists limitations and sources", () => {
    render(<AnswerView answer={toAnswerViewModel(ENVELOPE)} onOpenCitation={() => undefined} />);
    expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument();
    expect(screen.getByText("Interpretation:")).toBeInTheDocument();
    const limitations = screen.getByRole("heading", { name: "Limitations" }).parentElement!;
    expect(within(limitations).getByText("Tooling is not described.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Open citation E1/ })).toHaveLength(2);
  });

  it("shows provenance, the local excerpt and a labelled upstream link; Escape closes and restores focus", async () => {
    const user = userEvent.setup();
    const citation = toAnswerViewModel(ENVELOPE).citations[0];
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>open</button>
          {open && <EvidencePanel citation={citation} onClose={() => setOpen(false)} />}
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "open" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Inspection Definition/)).toBeInTheDocument();
    expect(within(dialog).getByText(/lines 28–29/)).toBeInTheDocument();
    expect(within(dialog).getByText(/formal reviews supported by a checklist/)).toBeInTheDocument();
    const link = within(dialog).getByRole("link", { name: "Open upstream source" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(dialog).getByText(/exact revision/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("shows the local excerpt without an upstream link", () => {
    const citation = { ...toAnswerViewModel(ENVELOPE).citations[0], upstreamUrl: null, revisionMatch: "unverified" as const };
    render(<EvidencePanel citation={citation} onClose={() => undefined} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/revision not verified/)).toBeInTheDocument();
    expect(screen.getByText(/formal reviews supported/)).toBeInTheDocument();
  });
});


describe("App shell, header, chat flow (T016, T018, T019)", () => {
  it("shows the header identity and switches tabs without reload", async () => {
    installFetch(baseRoutes());
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByText("Community project")).toBeInTheDocument();
    expect(screen.getByText("Runs on this computer")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await user.click(screen.getByRole("tab", { name: "Search" }));
    expect(screen.getByRole("heading", { name: "Search the documentation" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Search" })).toHaveAttribute("aria-selected", "true");
  });

  it("drives queued → validating → ready from the SSE stream and opens a citation", async () => {
    const mock = installFetch(baseRoutes({ "POST /api/v1/chat": () => sse(STREAM) }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await ask(user, "How are inspections performed?");
    await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
    expect(screen.getByText("Ready", { selector: ".status" })).toBeInTheDocument();
    const chatCall = mock.calls.find((c) => c.url === "/api/v1/chat")!;
    const body = JSON.parse(String(chatCall.init!.body));
    expect(body).toEqual({ question: "How are inspections performed?", snapshot_id: SNAPSHOT, history: [] });
    expect((chatCall.init!.headers as Record<string, string>).Accept).toBe("text/event-stream");
    await user.click(screen.getAllByRole("button", { name: /Open citation E1/ })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(mock.calls.every((c) => c.url.startsWith("/api/v1/") || c.url.startsWith("/health/"))).toBe(true);
  });

  it("sends the previous answer as snapshot-bound history on a follow-up", async () => {
    const mock = installFetch(baseRoutes({ "POST /api/v1/chat": () => sse(STREAM) }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await ask(user, "How are inspections performed?");
    await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
    await ask(user, "And who performs them?");
    await waitFor(() => expect(mock.calls.filter((c) => c.url === "/api/v1/chat")).toHaveLength(2));
    const second = JSON.parse(String(mock.calls.filter((c) => c.url === "/api/v1/chat")[1].init!.body));
    expect(second.history).toEqual([
      { role: "user", content: "How are inspections performed?" },
      {
        role: "assistant",
        content: "Inspections are formal reviews supported by a checklist.\nThis suggests a checklist is mandatory.",
        snapshot_id: SNAPSHOT,
      },
    ]);
  });

  it("blocks over-long questions using the server-provided limit", async () => {
    installFetch(baseRoutes());
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await user.type(screen.getByLabelText("Your question"), "x".repeat(201));
    expect(screen.getByText(/longer than 200 characters/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});

describe("Failure states, stop and retry (T021, T022)", () => {
  it("stop aborts the request and shows a retry that re-issues the same question", async () => {
    let chatCalls = 0;
    const mock = installFetch(
      baseRoutes({
        "POST /api/v1/chat": () => {
          chatCalls += 1;
          return chatCalls === 1
            ? sse([{ event: "progress", data: { stage: "generating" } }], { hold: true })
            : sse(STREAM);
        },
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await ask(user, "How are inspections performed?");
    await waitFor(() => expect(screen.getByText("Generating an answer", { selector: ".status" })).toBeInTheDocument());
    const signal = mock.calls.find((c) => c.url === "/api/v1/chat")!.init!.signal!;
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(signal.aborted).toBe(true);
    expect(screen.getByText("Stopped.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
    const bodies = mock.calls.filter((c) => c.url === "/api/v1/chat").map((c) => JSON.parse(String(c.init!.body)));
    expect(bodies.map((b) => b.question)).toEqual(["How are inspections performed?", "How are inspections performed?"]);
  });

  it("an error after progress keeps the turn and shows the reason with a retry", async () => {
    installFetch(
      baseRoutes({
        "POST /api/v1/chat": () =>
          sse([
            { event: "progress", data: { stage: "searching" } },
            { event: "error", data: { error: { code: "GENERATION_UNAVAILABLE", message: "down", request_id: "r", retryable: true } } },
            { event: "done", data: {} },
          ]),
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await ask(user, "q1");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("GENERATION_UNAVAILABLE"));
    expect(screen.getByText("Failed", { selector: ".status" })).toBeInTheDocument();
    expect(screen.getByText("q1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  });

  it("busy (429) is reported with a retry, no automatic retry", async () => {
    let calls = 0;
    installFetch(
      baseRoutes({
        "POST /api/v1/chat": () => {
          calls += 1;
          return json({ error: { code: "CHAT_BUSY", message: "busy", request_id: "r", retryable: true } }, 429);
        },
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await ask(user, "q");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Try again in a moment"));
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(calls).toBe(1);
  });

  it("chat unavailable but search available shows guidance", async () => {
    installFetch(
      baseRoutes({
        "GET /api/v1/capabilities": () =>
          json({
            ...CAPABILITIES,
            modes: {
              search: { available: true, reasons: [] },
              chat: { available: false, reasons: ["generation_model_missing"] },
              compare: { available: false, reasons: ["not_implemented"] },
            },
          }),
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/models pull/)).toBeInTheDocument());
    expect(screen.getByText(/search still works/)).toBeInTheDocument();
  });

  it("API unreachable on load shows a retry that re-fetches only when clicked", async () => {
    let capabilityCalls = 0;
    installFetch(
      baseRoutes({
        "GET /api/v1/capabilities": () => {
          capabilityCalls += 1;
          throw new TypeError("network down");
        },
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(capabilityCalls).toBe(1); // no background polling (FR-006a)
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(capabilityCalls).toBe(2));
  });
});
