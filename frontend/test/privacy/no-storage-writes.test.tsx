/**
 * T023 (FR-013, FR-014, FR-015, SC-004): a full ask → answer → export flow writes nothing to Web
 * Storage or cookies and never logs question or answer text to the console.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../src/App";
import { COMPARISON, ENVELOPE, SNAPSHOT, baseRoutes, compareRoutes, installFetch, sse } from "../helpers/fetch";

afterEach(() => vi.restoreAllMocks());

describe("privacy", () => {
  it("no storage, cookie or console writes carrying conversation text", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const cookie = vi.spyOn(document, "cookie", "set");
    const logs = ["log", "info", "warn", "error", "debug"].map((m) =>
      vi.spyOn(console, m as "log").mockImplementation(() => undefined),
    );
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: () => undefined });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const mock = installFetch(baseRoutes({ "POST /api/v1/chat": () => sse([{ event: "answer", data: ENVELOPE }, { event: "done", data: {} }]) }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    const question = "Secret question about inspections";
    await user.type(screen.getByLabelText("Your question"), question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Export Markdown" }));
    expect(setItem).not.toHaveBeenCalled();
    expect(cookie).not.toHaveBeenCalled();
    for (const spy of logs) {
      for (const args of spy.mock.calls) {
        const text = args.map(String).join(" ");
        expect(text).not.toContain(question);
        expect(text).not.toContain("formal reviews supported by a checklist");
      }
    }
    // FR-015: every request goes to this application's own API.
    expect(mock.calls.every((c) => /^\/(api\/v1|health)\//.test(c.url))).toBe(true);
    vi.unstubAllGlobals();
  });
});

describe("privacy of comparisons (F007 T025)", () => {
  it("compare → export writes no storage or cookies and calls only the application's API", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const cookie = vi.spyOn(document, "cookie", "set");
    const logs = ["log", "info", "warn", "error", "debug"].map((m) =>
      vi.spyOn(console, m as "log").mockImplementation(() => undefined),
    );
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: () => undefined });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const mock = installFetch(compareRoutes({
      "POST /api/v1/compare": () => sse([{ event: "comparison", data: COMPARISON }, { event: "done", data: {} }]),
    }));
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
    await user.click(screen.getByRole("tab", { name: "Compare" }));
    const question = "Secret comparison question";
    await user.type(screen.getByLabelText("Question to compare"), question);
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Differences" })).toBeInTheDocument());
    await user.click(screen.getAllByRole("button", { name: "Export JSON" }).at(-1)!);
    expect(setItem).not.toHaveBeenCalled();
    expect(cookie).not.toHaveBeenCalled();
    for (const spy of logs) {
      for (const args of spy.mock.calls) {
        expect(args.map(String).join(" ")).not.toContain(question);
      }
    }
    expect(mock.calls.every((c) => /^\/(api\/v1|health)\//.test(c.url))).toBe(true);
    vi.unstubAllGlobals();
  });
});
