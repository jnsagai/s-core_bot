// F006 FR-015 / T027: no analytics, crash-reporting or telemetry SDK may be a dependency or be
// imported anywhere in frontend/src.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const BANNED = [
  "@sentry/", "sentry", "posthog", "mixpanel", "amplitude", "segment", "analytics",
  "@datadog/", "newrelic", "bugsnag", "logrocket", "hotjar", "gtag", "google-analytics",
  "@vercel/analytics", "plausible", "matomo", "fullstory", "rollbar", "@opentelemetry/",
];

const root = new URL("../", import.meta.url).pathname;
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
const problems = deps.filter((d) => BANNED.some((b) => d === b || d.startsWith(b) || d.includes(b)))
  .map((d) => `dependency ${d}`);

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      walk(path);
    } else if (/\.(ts|tsx|js|jsx)$/.test(name)) {
      const text = readFileSync(path, "utf8");
      for (const match of text.matchAll(/(?:from|import)\s*\(?\s*["']([^"']+)["']/g)) {
        if (BANNED.some((b) => match[1].includes(b))) {
          problems.push(`${path}: imports ${match[1]}`);
        }
      }
    }
  }
}
walk(join(root, "src"));

if (problems.length) {
  console.error(`telemetry check FAILED:\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log(`telemetry check passed: ${deps.length} dependencies, no analytics/telemetry SDK`);
