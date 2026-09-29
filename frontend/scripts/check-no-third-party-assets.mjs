// F006 FR-012 / SC-002 / T034a: the built bundle must not reference any third-party host.
// - index.html: no absolute http(s) URL in src/href at all.
// - CSS: no absolute url(...) or @import.
// - JS: absolute URLs may only be reviewed inert string literals (XML namespaces, error-doc
//   links, SafeMarkdown's placeholder base) that the browser never fetches. Any new URL fails
//   and must be reviewed before it is added here.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const INERT_LITERALS = new Set([
  "http://www.w3.org/1999/xlink",
  "http://www.w3.org/2000/svg",
  "http://www.w3.org/XML/1998/namespace",
  "http://www.w3.org/1998/Math/MathML",
  "https://react.dev/errors/",
  "https://placeholder.invalid",
  "https://github.com/syntax-tree/hast-util-to-jsx-runtime",
]);
const URL_RE = /https?:\/\/[A-Za-z0-9.\-]+(?:\/[A-Za-z0-9._\-\/]*)?/g;

const dist = new URL("../dist/", import.meta.url).pathname;
const problems = [];

const html = readFileSync(join(dist, "index.html"), "utf8");
for (const match of html.matchAll(/(?:src|href)\s*=\s*["']([^"']+)["']/gi)) {
  if (/^(https?:)?\/\//i.test(match[1])) {
    problems.push(`index.html references ${match[1]}`);
  }
}

for (const name of readdirSync(join(dist, "assets"))) {
  const text = readFileSync(join(dist, "assets", name), "utf8");
  if (name.endsWith(".css")) {
    for (const match of text.matchAll(/url\(\s*["']?(https?:)?\/\/|@import/gi)) {
      problems.push(`${name}: external stylesheet reference near "${match[0]}"`);
    }
  }
  if (name.endsWith(".js")) {
    for (const match of text.matchAll(URL_RE)) {
      if (!INERT_LITERALS.has(match[0])) {
        problems.push(`${name}: unreviewed absolute URL ${match[0]}`);
      }
    }
  }
}

if (problems.length) {
  console.error(`third-party asset check FAILED:\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log("third-party asset check passed: no external asset references in dist/");
