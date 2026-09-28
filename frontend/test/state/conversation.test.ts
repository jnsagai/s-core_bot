import { describe, expect, it } from "vitest";
import {
  EMPTY_CONVERSATION,
  conversationReducer,
  toHistory,
  type ConversationState,
} from "../../src/state/conversation";

describe("conversationReducer", () => {
  it("adds a user turn and a queued assistant turn on ask", () => {
    const state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "What is S-CORE?",
      snapshotId: "snap-1",
    });

    expect(state.turns).toHaveLength(2);
    expect(state.turns[0]).toMatchObject({ role: "user", content: "What is S-CORE?" });
    expect(state.turns[1]).toMatchObject({ role: "assistant", status: "queued" });
    expect(state.snapshotId).toBe("snap-1");
  });

  it("applies progress, then answer events to the assistant turn", () => {
    let state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "hi",
      snapshotId: "snap-1",
    });
    const assistantId = state.turns[1].id;

    state = conversationReducer(state, {
      type: "streamEvent",
      turnId: assistantId,
      event: { event: "progress", id: 1, data: { stage: "searching" } },
    });
    expect(state.turns[1].status).toBe("searching");

    state = conversationReducer(state, {
      type: "streamEvent",
      turnId: assistantId,
      event: {
        event: "answer",
        id: 2,
        data: { snapshot_id: "snap-1", status: "answered", claims: [] },
      },
    });
    expect(state.turns[1].status).toBe("ready");
    expect(state.turns[1].answer).toMatchObject({ status: "answered" });
    expect(state.turns[1].snapshotId).toBe("snap-1");
  });

  it("marks the turn failed on an error event and preserves its progress history", () => {
    let state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "hi",
      snapshotId: "snap-1",
    });
    const assistantId = state.turns[1].id;
    state = conversationReducer(state, {
      type: "streamEvent",
      turnId: assistantId,
      event: { event: "progress", id: 1, data: { stage: "generating" } },
    });
    state = conversationReducer(state, {
      type: "streamEvent",
      turnId: assistantId,
      event: { event: "error", id: 2, data: { code: "ANSWER_INVALID" } },
    });

    expect(state.turns[1].status).toBe("failed");
    expect(state.turns[1].error).toMatchObject({ code: "ANSWER_INVALID" });
    expect(state.turns).toHaveLength(2);
  });

  it("marks a turn cancelled", () => {
    let state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "hi",
      snapshotId: "snap-1",
    });
    const assistantId = state.turns[1].id;
    state = conversationReducer(state, { type: "cancel", turnId: assistantId });
    expect(state.turns[1].status).toBe("cancelled");
  });

  it("clear removes all turns but keeps the bound snapshot", () => {
    let state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "hi",
      snapshotId: "snap-1",
    });
    state = conversationReducer(state, { type: "clear" });
    expect(state.turns).toHaveLength(0);
    expect(state.snapshotId).toBe("snap-1");
  });

  it("setSnapshot replaces the snapshot and clears all turns", () => {
    let state = conversationReducer(EMPTY_CONVERSATION, {
      type: "ask",
      question: "hi",
      snapshotId: "snap-1",
    });
    state = conversationReducer(state, { type: "setSnapshot", snapshotId: "snap-2" });
    expect(state.turns).toHaveLength(0);
    expect(state.snapshotId).toBe("snap-2");
  });
});

describe("toHistory", () => {
  it("includes user turns and only ready assistant turns with a snapshot binding", () => {
    const state: ConversationState = {
      snapshotId: "snap-1",
      turns: [
        { id: "1", role: "user", content: "q1" },
        { id: "2", role: "assistant", content: "a1", status: "ready", snapshotId: "snap-1" },
        { id: "3", role: "user", content: "q2" },
        { id: "4", role: "assistant", content: "", status: "generating" },
      ],
    };

    expect(toHistory(state)).toEqual([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1", snapshotId: "snap-1" },
      { role: "user", content: "q2" },
    ]);
  });
});
