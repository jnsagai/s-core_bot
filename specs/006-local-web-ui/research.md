# Research: F006 Local Web Experience and Privacy

Checked against the public npm registry on 2026-09-28 (registry lookups only — no packages
installed yet at research time; `node --version` on the workstation is v20.20.2).

## R1. Frontend dependency versions (FR-019, constitution technology constraint)

**Measured** (`npm view <pkg> version`):

| Package | Version | Role |
| --- | --- | --- |
| `react`, `react-dom` | 19.3.0 | UI runtime |
| `vite` | 8.3.1 | Build tool / dev server |
| `@vitejs/plugin-react` | 6.1.1 | Vite React plugin |
| `typescript` | 7.0.2 | Language/type checker |
| `react-markdown` | 10.1.0 | Markdown → React elements (no raw HTML by default, see R2) |
| `remark-gfm` | 4.0.1 | GitHub-flavoured Markdown (tables, strikethrough) for `react-markdown` |
| `vitest`, `@vitest/coverage-v8` | 5.0.2 | Test runner (no browser needed; jsdom environment) |
| `@testing-library/react` | 16.3.3 | Component rendering/queries |
| `@testing-library/user-event` | 14.6.7 | Keyboard/pointer simulation for a11y-relevant tests |
| `jsdom` | 30.1.1 | DOM environment for Vitest |
| `axe-core` | 4.13.0 | Static accessibility rule engine, run over jsdom-rendered markup |
| `eslint`, `typescript-eslint` | 10.11.0, 8.71.0 | Lint |
| `license-checker-rseidelsohn` | 5.0.1 | npm dependency license inventory (maintained fork; original `license-checker` is unmaintained) |
| `@types/react`, `@types/react-dom` | 19.3.0 | Type definitions matching the runtime major |

**Decision**: pin these exact versions in `frontend/package.json` and commit the resulting
`package-lock.json` (`npm install` once, then `npm ci` for every reproducible install per FR-019).

## R2. `react-markdown` does not render raw HTML by default (FR-009)

**Measured**: `npm view react-markdown dependencies` lists `mdast-util-to-hast`,
`remark-parse`, `remark-rehype`, `hast-util-to-jsx-runtime`, `unified` — no `rehype-raw` anywhere
in its dependency tree. `rehype-raw` is the plugin that turns embedded HTML nodes into real DOM;
without it, `react-markdown`'s pipeline parses raw HTML as a plain text/ignored node and never
calls `dangerouslySetInnerHTML`. This is a property of the library's own architecture (documented
behaviour, confirmed here by its actual dependency graph), not a configuration flag we could get
wrong later — the sanitizing behaviour is "don't add a package," which is easy to audit in a
future dependency review.

**Decision**: use `react-markdown` + `remark-gfm` only. Never add `rehype-raw` or
`rehype-sanitize` (the latter would imply raw HTML is intentionally allowed-then-filtered, which
is a strictly larger attack surface than never parsing it). Override the `a` and `img` element
renderers via `react-markdown`'s `components` prop:
- `a`: allow only `http://`/`https://` `href` values (anything else renders as inert text, not a
  link); always render with `rel="noopener noreferrer"` and `target="_blank"` for external hosts.
- `img`: never render an `<img>` element (which would trigger a network fetch); render the alt
  text and URL as a plain, clickable-as-a-link (same `a` rule) reference instead. This makes "no
  automatic remote image loads" (SEC-003) true by construction — there is no code path that emits
  an `<img src>` from Markdown at all.

## R3. SSE-over-`fetch()` for `POST /api/v1/chat` (master spec §10.1)

**Constraint**: the browser's built-in `EventSource` API only issues `GET` requests and cannot
set the request body or `Accept` header the F005 contract requires
(`specs/005-grounded-chat/contracts/http-api.md`). It also does not expose a way to know when the
`done` event was the true end vs. a connection drop, and it auto-reconnects, which
`specs/005-grounded-chat/spec.md` (§10.1: "browsers must not reconnect and silently duplicate
inference") explicitly forbids.

**Decision**: `chat.ts` calls `fetch(..., {method: "POST", headers: {Accept:
"text/event-stream"}, signal})` and reads `response.body` (a `ReadableStream<Uint8Array>`) with a
small hand-written frame parser that splits on blank lines, reads `id:`/`event:`/`data:` fields
per the contract, and never auto-retries. `AbortController` tied to the "Stop" button and to
component unmount aborts the fetch, which the F005 backend already treats as a client disconnect
(cancellation within 2 s per its FR-020). This is the same approach the master spec names
verbatim ("fetch-readable server-sent-event framing over POST").

## R4. Serving the static build from FastAPI (constitution technology constraint)

**Options considered**:
1. `fastapi.staticfiles.StaticFiles` mounted at `/`, plus an explicit `GET /` and any other
   non-API path returning `index.html` (SPA-fallback pattern) — the common approach for a
   client-routed SPA.
2. `StaticFiles` mounted at `/`, with **no** fallback route, because this app has no client-side
   router (Key Design Decision 1): the only HTML document is `/`, and Vite's default build emits
   hashed asset paths under `/assets/*` that `StaticFiles` serves directly.

**Decision**: option 2. `api/static_routes.py` mounts `frontend/dist` at `/` with `StaticFiles`
using `html=True` (serves `index.html` for `/`) and explicit 404 for anything under `/assets/*`
that does not exist as a built file — never a fallback to `index.html` for arbitrary paths, which
would otherwise let any path masquerade as "the app page" for the guard exemption in R5. Mounted
*after* all `/api/v1/*` and `/health/*` routers are registered, so API routes always take
precedence and a path collision is impossible by construction (FastAPI matches routers in
registration order for non-overlapping prefixes; `/api` and `/health` are disjoint from
`StaticFiles`'s `/`).

`vite.config.ts` sets `publicDir: false` (no separate unhashed-static-file copy step) so the
build's *only* output paths are `dist/index.html` and hashed files under `dist/assets/` — no
`favicon.ico`, `robots.txt`, or similar top-level file exists outside that set. This keeps R5's
guard-exemption predicate (`"/"` or starts with `"/assets/"`) a complete enumeration of what the
build actually emits, not an approximation that could silently miss a real path (checklist
CHK004).

The static response for `/` also carries a strict Content-Security-Policy (`default-src 'self';
script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self';
frame-ancestors 'none'; base-uri 'none'; form-action 'self'`) and no `X-Frame-Options` is needed
separately since `frame-ancestors` supersedes it in every browser this app targets (FR-010a).
`style-src 'unsafe-inline'` is required because Vite's default production CSS injection uses a
`<link>` tag, not inline `<style>`, for the app's own stylesheet — **verify during implementation
whether `'unsafe-inline'` for `style-src` can be dropped entirely** once the exact build output is
inspected; note this as a follow-up rather than assuming it either way.

## R5. Guard exemption for the static document (A-008 → A-034, FR-011a)

**Current code** (`src/score_docs_assistant/api/guard.py:108-113`): `HostOriginGuard` rejects any
request with header `Sec-Fetch-Site: cross-site` with `403 CROSS_SITE_REQUEST`, unconditionally,
before the request reaches any route. This is correct and necessary for `/api/v1/*`/`/health/*`
(a hostile page's script must never reach them, cross-site or not — SEC-004, AT-18) but wrong for
the one legitimate case of a human navigating their own browser to `http://127.0.0.1:<port>/`
from a bookmark or a link on another page, which browsers may also tag `Sec-Fetch-Site:
cross-site` for the top-level document request itself.

**Decision**: add one narrow, allowlist-shaped exemption keyed on the server's own route table,
not on client-supplied headers: `HostOriginGuard` is constructed with a
`static_get_paths: Callable[[str], bool]` predicate (in practice: `scope["method"] == "GET"` and
`path == "/"` or `path.startswith("/assets/")` — the fixed, known shape of a Vite build's output,
verified against the actual `frontend/dist` listing in a contract test rather than assumed). Only
for requests matching that predicate is the cross-site check skipped; the Host check still always
applies (so a hostile `Host` header is still rejected), and the exemption never touches
`/api/v1/*` or `/health/*` since those never match the predicate. This keeps SEC-004/AT-18's
guarantee exactly as strong as before for every state-changing or data-returning endpoint.

Exempting the cross-site *navigation* header check is a separate concern from *framing*
(checklist CHK005): a hostile page embedding the app in a hidden/disguised `<iframe>` for a
clickjacking attempt is not what `Sec-Fetch-Site` protects against at all — a framed load can
still report `same-origin` or `none` depending on browser/context, so the header check alone
would not stop it. R4's `frame-ancestors 'none'` CSP directive on the static response closes that
gap directly: no origin, including this one loaded elsewhere, may frame the page.

## R6. Accessibility checks without a real browser (constitution Principle VII)

**Constraint**: no Playwright/Chromium/Puppeteer browser may be installed or downloaded in this
environment (run constraint). `axe-core` can run against a jsdom-rendered DOM tree (it does not
require a real renderer for structural rules: missing labels, missing roles, invalid ARIA
attributes, heading order, landmark uniqueness), but several of its rules genuinely require a
real layout/paint engine (`color-contrast`, some `focus-order-semantics` checks) and either no-op
or produce unreliable results under jsdom.

**Decision**: run `axe-core` (via a small Vitest helper, not a heavier wrapper package) over the
rendered `App` tree in `test/a11y/main-screen.a11y.test.tsx`, restricted to the rule subset that
does not require real layout (documented explicitly in that test file's setup, not silently
assumed complete). Record in `verification.md`, honestly, that color-contrast and real
keyboard-focus-order verification are "not run — no browser on this machine," matching the
spec's own Assumptions section, rather than reporting a green a11y suite as if it were exhaustive.

## R7. npm dependency license inventory (FR-020, OPS-005)

**Decision**: add `license-checker-rseidelsohn` as a frontend devDependency (chosen over the
unmaintained original `license-checker`: last npm-registry publish recency and open issues were
compared via the registry metadata). `frontend/package.json` gets a `"license-check": "license-
checker-rseidelsohn --json"` script. `scripts/check_licenses.py` gains `run_npm_licenses()`,
which runs `npm run license-check --silent` with `cwd=frontend/` (only when `frontend/
package-lock.json` exists, so the Python-only test/lint path is unaffected before the frontend is
scaffolded) and feeds the parsed inventory through the exact same `evaluate()` / `is_allowed()` /
`is_copyleft()` functions and `config/license-exceptions.yaml` used for Python packages — one
policy, two inventories, per plan.md Key Design Decision 7.
