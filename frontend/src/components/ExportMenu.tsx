import { buildJsonExport, buildMarkdownExport } from "../answer/export";
import type { AnswerViewModel } from "../answer/model";

function download(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function ExportMenu({ answer }: { answer: AnswerViewModel }) {
  const stamp = () => new Date().toISOString();
  const base = () => `score-answer-${stamp().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z")}`;
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
