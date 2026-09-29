/**
 * In-memory conversation state (data-model.md ConversationTurn). Never written to
 * localStorage/sessionStorage/cookies (FR-013) — this module holds only React state.
 */
import type { ChatStreamEvent } from "../api/chat";
import { answerText, toAnswerViewModel } from "../answer/model";

export type TurnStatus =
  | "queued"
  | "searching"
  | "generating"
  | "validating"
  | "ready"
  | "cancelled"
  | "failed";

export interface ConversationTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  snapshotId?: string;
  status?: TurnStatus;
  position?: number;
  answer?: Record<string, unknown>;
  error?: Record<string, unknown>;
}

export interface ConversationState {
  snapshotId: string | null;
  turns: ConversationTurn[];
}

export const EMPTY_CONVERSATION: ConversationState = { snapshotId: null, turns: [] };

export function makeId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `turn-${Math.random().toString(36).slice(2)}`;
}

export type ConversationAction =
  | { type: "ask"; question: string; snapshotId: string | null; turnId?: string }
  | { type: "streamEvent"; turnId: string; event: ChatStreamEvent }
  | { type: "cancel"; turnId: string }
  | { type: "setSnapshot"; snapshotId: string }
  | { type: "clear" };

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case "ask": {
      const userTurn: ConversationTurn = { id: makeId(), role: "user", content: action.question };
      const assistantTurn: ConversationTurn = {
        id: action.turnId ?? makeId(),
        role: "assistant",
        content: "",
        status: "queued",
      };
      return {
        snapshotId: action.snapshotId ?? state.snapshotId,
        turns: [...state.turns, userTurn, assistantTurn],
      };
    }
    case "streamEvent": {
      return {
        ...state,
        turns: state.turns.map((turn) => {
          if (turn.id !== action.turnId) {
            return turn;
          }
          const { event } = action.event;
          if (turn.status === "cancelled") {
            return turn; // a stopped turn ignores late events
          }
          if (event === "progress") {
            const data = action.event.data as { stage: TurnStatus; position?: number };
            return { ...turn, status: data.stage, position: data.position };
          }
          if (event === "answer") {
            const answer = action.event.data;
            const snapshotId =
              typeof answer.snapshot_id === "string" ? answer.snapshot_id : undefined;
            const content = answerText(toAnswerViewModel(answer));
            return { ...turn, status: "ready", answer, snapshotId, content };
          }
          if (event === "error") {
            return { ...turn, status: "failed", error: action.event.data };
          }
          return turn;
        }),
      };
    }
    case "cancel": {
      return {
        ...state,
        turns: state.turns.map((turn) =>
          turn.id === action.turnId ? { ...turn, status: "cancelled" } : turn,
        ),
      };
    }
    case "setSnapshot": {
      return { snapshotId: action.snapshotId, turns: [] };
    }
    case "clear": {
      return { ...EMPTY_CONVERSATION, snapshotId: state.snapshotId };
    }
    default:
      return state;
  }
}

/** The bounded history sent to `/api/v1/chat` (F005 FR-016): only completed assistant turns
 * carrying their own snapshot binding, and the user turns that produced them. */
export function toHistory(
  state: ConversationState,
): { role: "user" | "assistant"; content: string; snapshotId?: string }[] {
  const history: { role: "user" | "assistant"; content: string; snapshotId?: string }[] = [];
  for (const turn of state.turns) {
    if (turn.role === "user") {
      history.push({ role: "user", content: turn.content });
    } else if (turn.status === "ready" && turn.snapshotId) {
      history.push({ role: "assistant", content: turn.content, snapshotId: turn.snapshotId });
    }
  }
  return history;
}
