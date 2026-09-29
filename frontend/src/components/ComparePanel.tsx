import { useEffect, useRef, useState } from "react";
import { streamCompare } from "../api/compare";
import { ApiError } from "../api/client";
import { download, exportStamp } from "../answer/download";
import type { CitationViewModel } from "../answer/model";
import { buildComparisonJson, buildComparisonMarkdown } from "../comparison/export";
import { toComparisonViewModel, type ComparisonViewModel } from "../comparison/model";
import type { AppReadinessState } from "../state/readiness";
import { AnswerView } from "./AnswerView";
import { DifferenceList } from "./DifferenceList";
import { EvidencePanel } from "./EvidencePanel";
import { SnapshotDiffTable } from "./SnapshotDiffTable";

type Phase = "idle" | "running" | "ready" | "failed" | "cancelled";

const STAGE_TEXT: Record<string, string> = {
  queued: "Queued",
  searching: "Searching the documentation",
  generating: "Generating an answer",
  validating: "Checking the answer against its sources",
  comparing: "Comparing the two snapshots",
};

const REASON_TEXT: Record<string, string> = {
  snapshots_insufficient:
    "Comparison needs two documentation snapshots. Build another one with `score-assistant index build` (it does not have to be activated).",
  generation_model_missing: "The answer model is not installed. Run `score-assistant models pull`.",
  model_identity_mismatch: "The installed answer model differs from the locked one. Run `score-assistant models pull`.",
  runtime_unreachable: "The local model runtime is not running.",
  corpus_missing: "No documentation snapshot is installed.",
};

function progressText(event: Record<string, unknown>): string {
  const stage = typeof event.stage === "string" ? event.stage : "";
  const side = event.side === "left" ? "Left snapshot: " : event.side === "right" ? "Right snapshot: " : "";
  const position = stage === "queued" && typeof event.position === "number" ? ` (position ${event.position})` : "";
  return `${side}${STAGE_TEXT[stage] ?? stage}${position}`;
}

function errorText(data: Record<string, unknown>): string {
  const inner = (data.error ?? data) as Record<string, unknown>;
  const code = typeof inner.code === "string" ? inner.code : "ERROR";
  const message = typeof inner.message === "string" ? inner.message : "The comparison failed.";
  const hints: Record<string, string> = {
    CHAT_BUSY: "Another answer or comparison is running. Try again in a moment.",
    DEADLINE_EXCEEDED: "The comparison took too long. Try a narrower question.",
    GENERATION_UNAVAILABLE: "The answer model is unavailable.",
  };
  return `${hints[code] ?? message} (${code})`;
}

/** Compare screen (F007 US4): two explicitly chosen snapshots, one question, side-labelled answers,
 * typed differences and both snapshot identities. Results stay in memory only. */
export function ComparePanel({
  readiness,
  onRetryReadiness,
  announce,
}: {
  readiness: AppReadinessState;
  onRetryReadiness: () => void;
  announce: (message: string) => void;
}) {
  const snapshots = readiness.snapshots;
  const [rightChoice, setRight] = useState<string | null>(null);
  const [leftChoice, setLeft] = useState<string | null>(null);
  // Defaults (FR-018): right = the active snapshot, left = the newest other queryable snapshot.
  const right = rightChoice ?? readiness.activeSnapshotId ?? snapshots[0]?.snapshotId ?? "";
  const left = leftChoice ?? snapshots.find((s) => s.snapshotId !== right)?.snapshotId ?? "";
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState("");
  const [result, setResult] = useState<ComparisonViewModel | null>(null);
  const [error, setError] = useState("");
  const [openCitation, setOpenCitation] = useState<CitationViewModel | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const controller = useRef<AbortController | null>(null);
  const limit = readiness.limits?.questionCharacters ?? null;

  useEffect(() => () => controller.current?.abort(), []);

  async function run(text: string) {
    const abort = new AbortController();
    controller.current = abort;
    setPhase("running");
    setResult(null);
    setError("");
    setLastQuestion(text);
    setProgress("Starting");
    announce("Comparison started");
    try {
      for await (const event of streamCompare(
        { question: text, leftSnapshotId: left, rightSnapshotId: right },
        abort.signal,
      )) {
        if (abort.signal.aborted) {
          return;
        }
        if (event.event === "progress") {
          const message = progressText(event.data);
          setProgress(message);
          announce(message);
        } else if (event.event === "comparison") {
          setResult(toComparisonViewModel(event.data));
          setPhase("ready");
          announce("Comparison ready");
        } else if (event.event === "error") {
          setError(errorText(event.data));
          setPhase("failed");
          announce("Comparison failed");
        }
      }
    } catch (caught) {
      if (abort.signal.aborted) {
        return;
      }
      const data =
        caught instanceof ApiError
          ? { error: { code: caught.code, message: caught.message } }
          : { error: { code: "NETWORK_ERROR", message: "The application API is unreachable." } };
      setError(errorText(data));
      setPhase("failed");
      announce("Comparison failed");
    } finally {
      if (controller.current === abort) {
        controller.current = null;
      }
    }
  }

  function stop() {
    controller.current?.abort();
    controller.current = null;
    setPhase("cancelled");
    announce("Comparison stopped");
  }

  const text = question.trim();
  const same = Boolean(left) && left === right;
  const tooLong = limit !== null && text.length > limit;
  const tooFew = snapshots.length < 2;
  const blocked = tooFew || same || !left || !right || tooLong || !text || phase === "running";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!blocked) {
      void run(text);
    }
  }

  function exportAs(kind: "md" | "json") {
    if (!result) {
      return;
    }
    const now = new Date().toISOString();
    const name = `score-comparison-${exportStamp(now)}.${kind}`;
    if (kind === "md") {
      download(buildComparisonMarkdown(result), name, "text/markdown");
    } else {
      download(JSON.stringify(buildComparisonJson(result, now), null, 2), name, "application/json");
    }
  }

  const option = (id: string) => {
    const s = snapshots.find((x) => x.snapshotId === id);
    return s ? `${s.snapshotId}${s.active ? " (active)" : ""} — ${s.createdAt.slice(0, 10)}` : id;
  };

  return (
    <section aria-labelledby="compare-heading">
      <h2 id="compare-heading">Compare two snapshots</h2>
      {tooFew ? (
        <p className="notice">{REASON_TEXT.snapshots_insufficient}</p>
      ) : (
        readiness.status === "ready" &&
        !readiness.compare.available && (
          <p className="notice">
            {REASON_TEXT[readiness.compare.reason ?? ""] ?? "Comparison is unavailable right now."}{" "}
            <button type="button" onClick={onRetryReadiness}>
              Check again
            </button>
          </p>
        )
      )}
      <form onSubmit={submit} className="compare-form">
        <div className="pickers">
          <label>
            Left snapshot
            <select value={left} onChange={(e) => setLeft(e.target.value)} disabled={phase === "running"}>
              {snapshots.map((s) => (
                <option key={s.snapshotId} value={s.snapshotId}>
                  {option(s.snapshotId)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Right snapshot
            <select value={right} onChange={(e) => setRight(e.target.value)} disabled={phase === "running"}>
              {snapshots.map((s) => (
                <option key={s.snapshotId} value={s.snapshotId}>
                  {option(s.snapshotId)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {same && (
          <p className="error" id="compare-same">
            Pick two different snapshots to compare.
          </p>
        )}
        <label htmlFor="compare-question">Question to compare</label>
        <textarea
          id="compare-question"
          value={question}
          rows={2}
          onChange={(e) => setQuestion(e.target.value)}
          aria-describedby="compare-help"
        />
        <p id="compare-help" className={tooLong ? "error" : "muted small"}>
          {tooLong
            ? `The question is longer than ${limit} characters; please shorten it.`
            : "Each snapshot answers separately; content found on only one side is reported as not established, never as removed."}
        </p>
        <div className="actions">
          <button type="submit" disabled={blocked}>
            Compare
          </button>
          {phase === "running" && (
            <button type="button" onClick={stop}>
              Stop
            </button>
          )}
        </div>
      </form>
      {phase === "running" && (
        <p className="status" data-status="running">
          {progress}
        </p>
      )}
      {phase === "failed" && (
        <p role="alert">
          {error}{" "}
          <button type="button" onClick={() => void run(lastQuestion)}>
            Retry
          </button>
        </p>
      )}
      {phase === "cancelled" && (
        <p>
          Stopped.{" "}
          <button type="button" onClick={() => void run(lastQuestion)} disabled={!lastQuestion}>
            Retry
          </button>
        </p>
      )}
      {phase === "ready" && result && (
        <div className="comparison">
          <SnapshotDiffTable diff={result.snapshots} />
          <h3>Differences</h3>
          {result.warnings.length > 0 && (
            <ul className="notice">
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          <DifferenceList result={result} onOpenCitation={setOpenCitation} />
          <div className="sides">
            <section aria-labelledby="left-answer">
              <h3 id="left-answer">Left: {result.left.snapshotId}</h3>
              <AnswerView answer={result.left} onOpenCitation={setOpenCitation} />
            </section>
            <section aria-labelledby="right-answer">
              <h3 id="right-answer">Right: {result.right.snapshotId}</h3>
              <AnswerView answer={result.right} onOpenCitation={setOpenCitation} />
            </section>
          </div>
          <div className="export" role="group" aria-label="Export this comparison">
            <button type="button" onClick={() => exportAs("md")}>
              Export Markdown
            </button>
            <button type="button" onClick={() => exportAs("json")}>
              Export JSON
            </button>
          </div>
        </div>
      )}
      {openCitation && <EvidencePanel citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  );
}
