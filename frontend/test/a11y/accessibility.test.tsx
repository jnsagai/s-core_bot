/**
 * T028, T029, T031 under jsdom. axe-core runs only rules that do not need real layout or paint;
 * `color-contrast` (needs computed paint) and anything depending on real focus rendering are
 * disabled here and recorded as "not run — no browser on this machine" (research.md R6).
 */
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { App } from "../../src/App";
import { Dialog } from "../../src/components/Dialog";
import { COMPARISON, ENVELOPE, SNAPSHOT, SNAPSHOTS, baseRoutes, compareRoutes, installFetch, sse } from "../helpers/fetch";

afterEach(() => vi.unstubAllGlobals());

const LAYOUT_RULES = { "color-contrast": { enabled: false }, "scrollable-region-focusable": { enabled: false } };

async function axeViolations(root: Element) {
  const result = await axe.run(root, { rules: LAYOUT_RULES });
  return result.violations.map((v) => `${v.id}: ${v.nodes.length}`);
}

async function withAnswer() {
  installFetch(baseRoutes({ "POST /api/v1/chat": () => sse([{ event: "answer", data: ENVELOPE }, { event: "done", data: {} }]) }));
  const user = userEvent.setup();
  const view = render(<App />);
  await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
  await user.type(screen.getByLabelText("Your question"), "How are inspections performed?");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(screen.getByText("Answered from the cited sources")).toBeInTheDocument());
  return { user, view };
}

describe("axe (T028)", () => {
  it("main screen with an answer has no violations (layout-independent rules)", async () => {
    const { view } = await withAnswer();
    expect(await axeViolations(view.container)).toEqual([]);
  });

  it("evidence dialog has no violations", async () => {
    const { user, view } = await withAnswer();
    await user.click(screen.getAllByRole("button", { name: /Open citation E1/ })[0]);
    expect(await axeViolations(view.container)).toEqual([]);
  });
});

async function withComparison() {
  installFetch(compareRoutes({
    "POST /api/v1/compare": () => sse([{ event: "comparison", data: COMPARISON }, { event: "done", data: {} }]),
  }));
  const user = userEvent.setup();
  const view = render(<App />);
  await waitFor(() => expect(screen.getByText(`Snapshot: ${SNAPSHOT}`)).toBeInTheDocument());
  await user.click(screen.getByRole("tab", { name: "Compare" }));
  await user.type(screen.getByLabelText("Question to compare"), "How are inspections performed?");
  await user.click(screen.getByRole("button", { name: "Compare" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Differences" })).toBeInTheDocument());
  return { user, view };
}

describe("Compare tab accessibility (F007 T025, FR-018)", () => {
  it("has no axe violations with a result and with a side's evidence dialog open", async () => {
    const { user, view } = await withComparison();
    expect(await axeViolations(view.container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: /Open left evidence L1/ }));
    expect(await axeViolations(view.container)).toEqual([]);
  });

  it("reaches pickers, question, compare, differences' evidence and export by keyboard", async () => {
    const { user } = await withComparison();
    screen.getByLabelText("Left snapshot").focus();
    const reached: string[] = [];
    for (let i = 0; i < 40; i++) {
      const el = document.activeElement as HTMLElement;
      const name = el.getAttribute("aria-label") || (el as HTMLInputElement).labels?.[0]?.textContent || el.textContent || "";
      expect(name.trim(), `unnamed ${el.tagName}`).not.toBe("");
      reached.push(name.trim());
      await user.tab();
    }
    for (const name of ["Left snapshot", "Right snapshot", "Question to compare", "Compare", "Open left evidence L1", "Open right evidence R1", "Export Markdown"]) {
      expect(reached.some((r) => r.startsWith(name)), name).toBe(true);
    }
  });
});

describe("keyboard order (T029, FR-003)", () => {
  it("every control is reachable by Tab in a logical order with an accessible name", async () => {
    const { user } = await withAnswer();
    document.body.focus();
    const reached: string[] = [];
    for (let i = 0; i < 40; i++) {
      await user.tab();
      const el = document.activeElement as HTMLElement;
      if (!el || el === document.body) break;
      const name = el.getAttribute("aria-label") || (el as HTMLInputElement).labels?.[0]?.textContent || el.textContent || "";
      expect(name.trim(), `unnamed ${el.tagName}`).not.toBe("");
      reached.push(name.trim());
      if (reached.length > 1 && reached[0] === reached[reached.length - 1]) break;
    }
    const order = ["Documentation snapshot", "New conversation", "Ask", "Search", "Status"];
    const positions = order.map((n) => reached.findIndex((r) => r === n || r.startsWith(n)));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    for (const name of ["Open citation E1", "Export Markdown", "Export JSON", "Your question"]) {
      expect(reached.some((r) => r.startsWith(name)), name).toBe(true);
    }
  });
});

describe("focus trap (T031, US4 AS3)", () => {
  it("Tab cycles inside the dialog and Escape restores focus", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>opener</button>
          <button type="button">outside</button>
          {open && (
            <Dialog title="Test" onClose={() => setOpen(false)}>
              <button type="button">first</button>
              <button type="button">last</button>
            </Dialog>
          )}
        </>
      );
    }
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "opener" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "first" })).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "last" })).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "first" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole("button", { name: "last" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "opener" })).toHaveFocus();
  });

  it("snapshot confirmation dialog traps focus and restores it on cancel", async () => {
    const { user } = await withAnswer();
    const select = screen.getByLabelText("Documentation snapshot");
    select.focus();
    await user.selectOptions(select, SNAPSHOTS.snapshots[1].snapshot_id);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Switch and clear" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(select).toHaveFocus();
  });
});
