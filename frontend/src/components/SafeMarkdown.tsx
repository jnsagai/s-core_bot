import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders Markdown from answers/excerpts safely (FR-009, FR-010, SEC-003). `react-markdown`
 * without the `rehype-raw` plugin never turns embedded raw HTML into real DOM (research.md R2) —
 * that plugin is deliberately never added here. Links are restricted to `http(s)` and always
 * open safely; images are never rendered as an `<img>` (no automatic remote fetch is possible
 * because no such element is ever created), shown instead as a plain reference.
 */

const SAFE_SCHEMES = ["http:", "https:"];

function isSafeUrl(href: string): boolean {
  try {
    const url = new URL(href, "https://placeholder.invalid");
    return SAFE_SCHEMES.includes(url.protocol);
  } catch {
    return false;
  }
}

function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  if (!href || !isSafeUrl(href)) {
    return <span>{children}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function ImageReference({ src, alt }: { src?: string; alt?: string }) {
  const label = alt || "image";
  if (!src || !isSafeUrl(src)) {
    return <span>[{label}]</span>;
  }
  return <SafeLink href={src}>{`[${label}]`}</SafeLink>;
}

function extractText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(extractText).join("");
  }
  if (
    node !== null &&
    typeof node === "object" &&
    "props" in node &&
    node.props &&
    typeof node.props === "object" &&
    "children" in node.props
  ) {
    return extractText((node.props as { children?: React.ReactNode }).children);
  }
  return "";
}

function CodeBlock({ children }: { children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = extractText(children);
  return (
    <div>
      <pre>
        <code>{children}</code>
      </pre>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard
            .writeText(text)
            .then(() => setCopied(true))
            .catch(() => undefined);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

const components: Components = {
  a: SafeLink,
  img: ImageReference,
  pre: CodeBlock,
};

export function SafeMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {text}
    </ReactMarkdown>
  );
}
