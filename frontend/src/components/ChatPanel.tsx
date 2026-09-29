import { useEffect, useRef, useState, type Dispatch } from "react";
import { streamChat } from "../api/chat";
import { ApiError } from "../api/client";
import { toAnswerViewModel, type CitationViewModel } from "../answer/model";
import {
  makeId,
  toHistory,
  type ConversationAction,
  type ConversationState,
  type ConversationTurn,
} from "../state/conversation";
import type { AppReadinessState } from "../state/readiness";
import { AnswerView } from "./AnswerView";
import { EvidencePanel } from "./EvidencePanel";
import { ExportMenu } from "./ExportMenu";
import { STATUS_LABELS } from "../state/status";
import { StatusBadge } from "./StatusBadge";

const REASON_TEXT: Record<string, string> = {
  generation_model_missing:
    "The answer model is not installed. Run `score-assistant models pull`; search still works.",
  model_identity_mismatch:
    "The installed answer model differs from the locked one. Run `score-assistant models pull`; search still works.",
  runtime_unreachable: "The local model runtime is not running. Search still works.",
  corpus_missing:
    "No documentation snapshot is installed. Run `score-assistant index build --activate`.",
};

function errorMessage(error: Record<string, unknown> | undefined): string {
  const inner = (error?.error ?? error ?? {}) as Record<string, unknown>;
  const code = typeof inner.code === "string" ? inner.code : "ERROR";
  const message = typeof inner.message === "string" ? inner.message : "The request failed.";
  const hints: Record<string, string> = {
    CHAT_BUSY: "Another answer is being generated. Try again in a moment.",
    DEADLINE_EXCEEDED: "The answer took too long. Try a narrower question.",
    GENERATION_UNAVAILABLE: "The answer model is unavailable; search still works.",
  };
  return `${hints[code] ?? message} (${code})`;
}

/** Chat screen (UX-001, UX-003): ask, follow progress, stop, retry, open citations, export. */
export function ChatPanel({
  conversation,
  dispatch,
  readiness,
  onRetryReadiness,
  announce,
}: {
  conversation: ConversationState;
  dispatch: Dispatch<ConversationAction>;
  readiness: AppReadinessState;
  onRetryReadiness: () => void;
  announce: (message: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [openCitation, setOpenCitation] = useState<CitationViewModel | null>(null);
  const controller = useRef<AbortController | null>(null);
  const limit = readiness.limits?.questionCharacters ?? null;
  const running = conversation.turns.some(
    (t) => t.role === "assistant" && ["queued", "searching", "generating", "validating"].includes(t.status ?? ""),
  );

  useEffect(() => () => controller.current?.abort(), []);

  const last = conversation.turns[conversation.turns.length - 1];
  useEffect(() => {
    if (last?.role === "assistant" && last.status) {
      announce(STATUS_LABELS[last.status]);
    }
  }, [last?.role, last?.status, announce]);

  async function ask(text: string) {
    const history = toHistory(conversation);
    const turnId = makeId();
    dispatch({ type: "ask", question: text, snapshotId: conversation.snapshotId, turnId });
    const abort = new AbortController();
    controller.current = abort;
    try {
      for await (const event of streamChat(
        { question: text, snapshotId: conversation.snapshotId, history },
        abort.signal,
      )) {
        dispatch({ type: "streamEvent", turnId, event });
      }
    } catch (error) {
      if (abort.signal.aborted) {
        return;
      }
      const payload =
        error instanceof ApiError
          ? { error: { code: error.code, message: error.message } }
          : { error: { code: "NETWORK_ERROR", message: "The application API is unreachable." } };
      dispatch({ type: "streamEvent", turnId, event: { event: "error", id: 0, data: payload } });
    } finally {
      if (controller.current === abort) {
        controller.current = null;
      }
    }
  }

  function stop() {
    const current = conversation.turns[conversation.turns.length - 1];
    controller.current?.abort();
    controller.current = null;
    if (current?.role === "assistant") {
      dispatch({ type: "cancel", turnId: current.id });
    }
  }

  function questionFor(turn: ConversationTurn): string {
    const index = conversation.turns.indexOf(turn);
    return index > 0 ? conversation.turns[index - 1].content : "";
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || running || (limit !== null && text.length > limit)) {
      return;
    }
    setQuestion("");
    void ask(text);
  }

  const tooLong = limit !== null && question.trim().length > limit;
  const chatUnavailable = readiness.status === "ready" && !readiness.chat.available;

  return (
    <section aria-labelledby="chat-heading">
      <h2 id="chat-heading">Ask the documentation</h2>
      {readiness.status === "failed" && (
        <p className="notice" role="alert">
          {readiness.error} <button type="button" onClick={onRetryReadiness}>Retry</button>
        </p>
      )}
      {chatUnavailable && (
        <p className="notice">
          {REASON_TEXT[readiness.chat.reason ?? ""] ?? "Answers are unavailable right now; search still works."}{" "}
          <button type="button" onClick={onRetryReadiness}>
            Check again
          </button>
        </p>
      )}
      <ol className="turns">
        {conversation.turns.map((turn) =>
          turn.role === "user" ? (
            <li key={turn.id} className="turn turn-user">
              <p>
                <strong>You:</strong> {turn.content}
              </p>
            </li>
          ) : (
            <li key={turn.id} className="turn turn-assistant">
              {turn.status && <StatusBadge status={turn.status} position={turn.position} />}
              {turn.status === "ready" && turn.answer && (
                <>
                  <AnswerView answer={toAnswerViewModel(turn.answer)} onOpenCitation={setOpenCitation} />
                  <ExportMenu answer={toAnswerViewModel(turn.answer)} />
                </>
              )}
              {turn.status === "failed" && (
                <p role="alert">
                  {errorMessage(turn.error)}{" "}
                  <button type="button" onClick={() => void ask(questionFor(turn))} disabled={running}>
                    Retry
                  </button>
                </p>
              )}
              {turn.status === "cancelled" && (
                <p>
                  Stopped.{" "}
                  <button type="button" onClick={() => void ask(questionFor(turn))} disabled={running}>
                    Retry
                  </button>
                </p>
              )}
            </li>
          ),
        )}
      </ol>
      <form onSubmit={submit} className="ask">
        <label htmlFor="question">Your question</label>
        <textarea
          id="question"
          value={question}
          rows={3}
          onChange={(e) => setQuestion(e.target.value)}
          aria-describedby="question-help"
        />
        <p id="question-help" className={tooLong ? "error" : "muted small"}>
          {tooLong
            ? `The question is longer than ${limit} characters; please shorten it.`
            : "Answers cite the local documentation snapshot. Check cited sources for engineering decisions."}
        </p>
        <div className="actions">
          <button type="submit" disabled={running || !question.trim() || tooLong}>
            Ask
          </button>
          {running && (
            <button type="button" onClick={stop}>
              Stop
            </button>
          )}
        </div>
      </form>
      {openCitation && <EvidencePanel citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  );
}
