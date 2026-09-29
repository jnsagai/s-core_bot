import { buildJsonExport, buildMarkdownExport } from "../answer/export";
import { download, exportStamp } from "../answer/download";
import type { AnswerViewModel } from "../answer/model";

export function ExportMenu({ answer }: { answer: AnswerViewModel }) {
  const stamp = () => new Date().toISOString();
  const base = () => `score-answer-${exportStamp(stamp())}`;
  return (
    <div className="export" role="group" aria-label="Export this answer">
      <button
        type="button"
        onClick={() => download(buildMarkdownExport(answer), `${base()}.md`, "text/markdown")}
      >
        Export Markdown
      </button>
      <button
        type="button"
        onClick={() =>
          download(JSON.stringify(buildJsonExport(answer, stamp()), null, 2), `${base()}.json`, "application/json")
        }
      >
        Export JSON
      </button>
    </div>
  );
}
