# Day 28 — Guarded HTTP procurement chat over the real ProcureRAG service

Linear: **HER-296 — Day 28 loop: guarded HTTP procurement chat over the real ProcureRAG service**

Related gate: **HER-271 — Week 6 gate: live AI portfolio, ProcureRAG demo and readiness**

Date started: **2026-10-27**

## Mission

Build and prove the first **local, end-to-end, browser-facing procurement-chat vertical slice**:

```text
browser
  -> same-origin Next.js POST /api/chat
  -> authenticated HTTP POST /query
  -> the real ProcureRAG FastAPI service
  -> a reduced, typed browser response
```

Day 28 is about the product and security boundary, not public launch. The result must work locally, use the real HTTP service boundary, preserve every typed ProcureRAG outcome, and fail closed when credentials, input, upstream transport, or response validation are wrong.

## Ownership and non-negotiable boundary

Juan owns every implementation decision and every change to:

- ProcureRAG `src/*.py` and `tests/test_*.py`;
- the portfolio's TypeScript, React, CSS, tests, lockfile, and assets;
- model/provider selection and any paid call;
- Vercel, Azure, OpenRouter, secrets, accounts, deployment, and spending.

Hermes may create and maintain this route, the learning-log evidence scaffold, Linear status/comments, review findings, and the final quiz. Hermes must not implement the Python or TypeScript solution.

### Explicitly out of scope today

- no Azure re-provisioning;
- no Vercel deployment or repository linking;
- no public URL or legacy-site cutover;
- no persistent Redis-compatible quota or production admission script;
- no production kill-switch storage;
- no custom domain, analytics, remote MCP, uploads, writes, role picker, or approval UI;
- no claim that the demo is public or production-ready;
- no paid LLM call until the model, output cap, worst-case cost, daily cap, and provider-key credit limit are written down and Juan explicitly approves the smoke.

Day 29 owns hosted-chain provisioning, persistent atomic quota, deployed kill-switch proof, launch smoke, and rollback. Day 30 owns public URL/cutover, canonical metadata, share image, legacy CV redirect, LinkedIn reconciliation, and the weekly gate.

---

## Course and source checkpoint

There is no new Boot.dev chapter today. Day 28 is the Week 6 product/security slice, driven by the accepted architecture contract and official framework/provider documentation.

Read the named sections before implementing, then record one applied decision or rejection per source in the learning log.

### Required sources

1. **Accepted architecture contract** — portfolio `docs/adr/portfolio-demo-architecture.md` - READ
   - §3 Decision;
   - §6 The contract, especially §6.1 browser → BFF, §6.2 BFF → API, and §6.3 response mapping;
   - §7 Public data, role and trust policy;
   - §8.1 Upstream authentication and secrets;
   - §8.2 Spend ceilings;
   - §8.3 Quota, concurrency and bounds;
   - §8.4 Timeouts and cold start;
   - §10 Quality gate;
   - §11 open decisions 1–4 and 10.

2. **ProcureRAG contract probe** — `scripts/portfolio_contract_probe.py`, full file - READ
   - `BrowserQuestion`, `build_upstream_request`, `BrowserView`;
   - `handle_browser_request` ordering;
   - all nineteen scenarios;
   - `check_public_presets` and `check_browser_view`.

3. **Next.js Route Handlers** — <https://nextjs.org/docs/app/getting-started/route-handlers> - READ
   - file convention and supported methods;
   - request body handling;
   - route-handler runtime behavior and caching;
   - CORS section, to explain why a same-origin BFF does **not** need browser-to-FastAPI CORS.

4. **Next.js environment variables** — <https://nextjs.org/docs/app/guides/environment-variables> - READ
   - loading environment variables;
   - bundling for the browser with `NEXT_PUBLIC_`;
   - runtime environment variables;
   - test environment variables.

5. **FastAPI Security Tools** — <https://fastapi.tiangolo.com/reference/security/> - READ
   - `HTTPBearer`;
   - `HTTPAuthorizationCredentials`;
   - `auto_error` behavior;
   - what the helper extracts versus what the application must still validate.

6. **Python `secrets.compare_digest`** — <https://docs.python.org/3/library/secrets.html#secrets.compare_digest> - READ
   - why secret comparison should use a constant-time helper instead of `==`.

7. **OpenRouter authentication and limits** - READ
   - <https://openrouter.ai/docs/api_reference/authentication> — key creation, Bearer authentication, and per-key credit limits;
   - <https://openrouter.ai/docs/api-reference/limits> — `GET /api/v1/key`, `limit`, `limit_remaining`, budgets, and failure modes;
   - <https://openrouter.ai/docs/features/privacy-and-logging> — training controls, provider logging/retention, and provider-policy filtering.

8. **Vercel Functions** - READ
   - <https://vercel.com/docs/functions/configuring-functions/duration> — App Router `maxDuration` and current Hobby limit;
   - <https://vercel.com/docs/functions/configuring-functions/region> — default region, single-region Hobby constraint, and `dub1` availability;
   - the current Hobby terms applicable to Juan's personal portfolio before any account/repository link.

### Reading record

- [ ] Accepted ADR read; applied/rejected decision recorded.
- [ ] Python contract probe read; applied/rejected decision recorded.
- [ ] Next.js Route Handlers read; applied/rejected decision recorded.
- [ ] Next.js environment-variable guide read; applied/rejected decision recorded.
- [ ] FastAPI `HTTPBearer` reference read; applied/rejected decision recorded.
- [ ] `secrets.compare_digest` reference read; applied/rejected decision recorded.
- [ ] OpenRouter authentication, limits, and privacy pages read; applied/rejected decision recorded.
- [ ] Vercel duration, region, and current Hobby terms read; applied/rejected decision recorded.

---

## Starting truth — measured at kickoff

### ProcureRAG

```text
branch: day-28
base: main @ dd8d0984a5e9cf75bb94d0fd5ff8eca0967a0e2d
origin/main divergence before branch: 0/0
working tree before scaffold: clean
Python: 3.11.15
uv: 0.11.11
```

Provider calls, tracing, and telemetry were disabled for every baseline command:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
DEEPEVAL_TELEMETRY_OPT_OUT=1
OMP_NUM_THREADS=1
```

Measured baseline:

```text
uv sync --locked --dev: exit 0
uv lock --check: exit 0
pytest: exit 0, 452 passed
compileall src tests scripts: exit 0
Ruff src tests scripts: exit 0, All checks passed
frozen fixture regression: exit 0, 7/7 as expected
current retrieval verification: exit 0, 6/6 [OK]
graph regression: exit 0, 6/6 contracts; 4 stand-in LLM calls
no-paid portfolio contract probe: exit 0, 19/19 scenarios + 2/2 contract checks
Q091: still red for live-answer completeness; deterministic Band 3 term gap remains named
git diff --check: exit 0
```

Current API truth:

- public routes: unauthenticated `GET /health`, `POST /query`, `POST /query/stream`;
- service-token constants/dependency: absent;
- CORS middleware: absent, which is correct for the accepted same-origin BFF design;
- rate limiting: process-local and learning-grade;
- live LLM: opt-in and off by default;
- no Azure service exists today.

### Portfolio

```text
branch: origin/day-27-preview
head: 530dfe41a51144cd1c01405884993bd84bca6728
remote divergence: 0/0
working tree in fresh audit clone: clean
Node: 22.22.2
npm: 10.9.7
Next.js: 16.4.3
```

Measured baseline:

```text
npm ci: exit 0, 354 packages added, 0 vulnerabilities
npm run typecheck: exit 0
npm run lint: exit 0
npm run build: exit 0; /, /about, /procurerag and /icon.svg static
npm test: exit 0, 67 passed
```

Current portfolio truth:

- the demo section is static and says `Live demo: in progress`;
- there is no `app/api/chat/route.ts`, BFF, chat Client Component, server credential, or `.env*` file;
- approved presets are Q001, Q005, Q021, and Q090; Q091/Q092 are withheld;
- `master` still publishes the legacy Jekyll site and is not touched by Day 28.

### Prerequisite status

- HER-295 / Day 27: **Done**.
- HER-296 / Day 28: moved to **In Progress** at kickoff.
- Nothing is deployed.

---

## Definition of done

Day 28 passes only when all of these are true.

### ProcureRAG service boundary

- [ ] `POST /query` requires the dedicated service credential.
- [ ] `POST /query/stream` requires the same credential, even though the browser-facing slice uses JSON `/query` only.
- [ ] `GET /health` remains unauthenticated and provider-free.
- [ ] Missing, malformed, wrong, and blank credentials fail with 401 before rate limiting, request validation, retrieval, or an LLM call.
- [ ] Correct credentials preserve every existing API status and do not alter role filtering or guard behavior.
- [ ] Secret comparison is constant-time.
- [ ] The service token never appears in a response, log, test output, trace, fixture, committed file, or docs.
- [ ] OpenAPI accurately declares the Bearer scheme on protected routes and not on `/health`.

### Same-origin BFF

- [ ] The browser may send only `{ "question": string }`; every extra key is rejected.
- [ ] The raw body is bounded to 2,048 bytes before JSON parsing and stops reading after 2,049 bytes.
- [ ] Questions are 1–500 characters.
- [ ] The BFF fixes the upstream role to `requester`.
- [ ] A `query_id` is attached only for an exact approved preset text.
- [ ] No public request can carry a role, reviewer decision, upload, or approval action.
- [ ] The BFF sends `Authorization: Bearer <service-token>` from a server-only environment variable.
- [ ] The BFF validates the complete upstream JSON response before reducing it to the browser shape.
- [ ] The browser response excludes `run_id`, `approval_request`, guard detail text, snippets, raw upstream bodies, and all secrets.
- [ ] There is exactly one upstream call and no automatic retry.
- [ ] Upstream timeout is 75 seconds and the route `maxDuration` is 100 seconds, unless an evidence-backed change is recorded.
- [ ] Same-origin browser traffic uses no CORS workaround and never calls FastAPI directly.

### Browser UI

- [ ] The chat is the smallest possible Client Component island inside the server-rendered `/procurerag` route.
- [ ] The rest of the case study remains readable with JavaScript disabled.
- [ ] Q001, Q005, Q021, and Q090 are the only presets.
- [ ] Q091 and Q092 stay withheld and are never offered as buttons.
- [ ] Every API/transport result maps to its distinct state: `answered`, `model_declined`, `gap_report`, `not_generated`, `blocked`, `pending_approval`, `invalid_question`, `busy`, `timed_out`, or `unavailable`.
- [ ] `pending_approval` fails closed; there is no approve/edit/reject UI.
- [ ] Free text shows the evidence-unchecked caveat.
- [ ] Sources are document/chunk IDs plus `cited`; no snippets or confidential document ids appear.
- [ ] Visible history is page-local only and is not model memory.
- [ ] Keyboard, focus, labels, status announcements, 320 px reflow, reduced motion, and no-JavaScript behavior are verified.
- [ ] A disabled/offline chat does not break the case study, CV, or code links.

### Local real-HTTP proof

- [ ] The browser calls the real local Next.js route.
- [ ] The Next.js route calls a separately running real FastAPI server over HTTP.
- [ ] Direct unauthenticated `/query` and `/query/stream` calls return 401.
- [ ] An authenticated request reaches the real guarded service.
- [ ] With live LLM off, a complete-evidence request returns `not_generated`; no provider call occurs.
- [ ] Tests may use fake retrieval/LLM boundaries, but the integration smoke must not replace HTTP with an in-process function call.
- [ ] No Azure/Vercel resource or public URL is implied by the local proof.

### Economics and provisioning gate

- [ ] The chosen model and exact current provider endpoint are recorded.
- [ ] Current input/output prices and source date are recorded.
- [ ] Public output cap is configured below the current 3,000-token default.
- [ ] Worst-case cost/request is calculated from the maximum allowed input/context/output, not from an average.
- [ ] Global daily cap is calculated from the approved US$5/month LLM ceiling.
- [ ] A dedicated OpenRouter key with a US$5 credit limit is confirmed before any paid smoke.
- [ ] Privacy/training/retention settings and remaining disclosure work are recorded.
- [ ] Juan explicitly approves any paid smoke; otherwise Day 28 closes with a no-paid local slice.
- [ ] Vercel Hobby terms fit and `dub1` availability are recorded, but provisioning remains Day 29.

---

## Implementation route

## Block 0 — reactivate the accepted contract

Before coding:

1. Create the portfolio implementation branch from `day-27-preview` @ `530dfe4`.
   - Suggested name: `day-28-chat`.
   - Record its exact base SHA.
   - Keep `master` and GitHub Pages untouched.
2. Confirm the ProcureRAG implementation branch is `day-28` from `main` @ `dd8d098`.
3. Read the source checkpoint and write the applied decisions.
4. Draw the two runtime trust boundaries:
   - browser → same-origin BFF: no credential, question only;
   - BFF → FastAPI: dedicated service credential and fixed `requester` role.
5. State the difference between:
   - service authentication: proves the request came through the BFF;
   - role authorization: restricts visible document labels;
   - visitor identity: **not implemented**.
6. Re-run both baselines before implementation if either branch head changed.

**Stop condition:** if the Day 27 portfolio head, accepted ADR, or ProcureRAG API contract has drifted, reconcile that drift before implementation.

## Block 1 — protect the real FastAPI query routes

Implement the smallest service-token boundary that satisfies the ADR.

### Required behavior

- Use one dedicated setting name consistently; the ADR names `PROCURERAG_SERVICE_TOKEN`.
- Parse the standard `Authorization: Bearer <service-token>` header with a FastAPI security helper or an equally explicit dependency.
- Validate the supplied token against the configured token with `secrets.compare_digest`.
- Return 401 with an appropriate `WWW-Authenticate: Bearer` header for missing, malformed, blank, or wrong credentials.
- Attach authentication to both `/query` and `/query/stream`.
- Keep `/health` open.
- Order dependencies so authentication runs before the rate limiter and checked request body.
- Fail closed if the configured token is absent or blank. Record whether this happens at process startup or request time and why.
- Never put the token in exception text, logs, reprs, snapshots, or test ids.

### Required tests

Add focused tests that prove:

1. `/health` returns 200 without a credential and does not build/call the provider.
2. `/query` returns 401 for no header.
3. `/query` returns 401 for a wrong scheme, blank token, and wrong token.
4. `/query/stream` has the same protection.
5. A correct token preserves a representative success path.
6. A missing/wrong token plus malformed JSON returns 401, proving auth wins over body validation.
7. A refused credential does not consume the rate-limit budget.
8. A refused credential performs zero retrieval and zero LLM calls.
9. OpenAPI marks only the protected routes with Bearer authentication.
10. Token values are absent from captured logs and response bodies.

Re-run every existing API test. Do not weaken old unauthenticated test helpers silently: update helpers so a protected request is intentional and visible.

### Documentation to reconcile

The top-level `src/api.py` explanation, README API surface, Docker/Azure runbooks, test queries, and the contract probe currently describe an unauthenticated service. Update only the documents whose instructions would become false.

Do not call the service "user authenticated". This token authenticates one BFF service, not a person.

## Block 2 — implement the typed Next.js BFF

Use a Node.js App Router Route Handler at `POST /api/chat`. Keep networking, validation, response reduction, and UI concerns separable enough to test independently.

### Server-only configuration

The BFF needs two server-only values:

- `PROCURERAG_API_URL`;
- `PROCURERAG_SERVICE_TOKEN`.

Rules:

- no `NEXT_PUBLIC_` prefix;
- no client import of a module that reads them;
- no committed `.env*` file;
- no fallback credential;
- blank/missing values fail closed as `unavailable`;
- log only configuration names/types, never values.

### Raw body and browser schema

The route must:

1. reject a declared `Content-Length` above 2,048 bytes without reading the body;
2. still enforce the limit while streaming the raw body, because chunked requests may omit `Content-Length`;
3. stop after at most 2,049 bytes;
4. reject invalid UTF-8/JSON, non-object JSON, arrays, missing `question`, extra keys, blank questions, and >500 characters;
5. call upstream zero times on every rejected body.

Do not use `request.json()` before enforcing the raw-byte cap.

### Upstream request

Build exactly:

```text
{ query: question, role: "requester" }
```

Add `query_id` only when the question text exactly equals one approved preset. Never add `decision`.

Send one HTTPS/HTTP request to `{PROCURERAG_API_URL}/query` with:

- `Authorization: Bearer <service-token>`;
- `Content-Type: application/json`;
- a 75-second abort timeout;
- no automatic retry.

The first slice uses JSON `/query`, not `/query/stream`.

### Validate, then reduce

Treat every upstream response as untrusted.

- Validate the complete `QueryResponse` discriminated shape before exposing any field.
- A 200 with invalid JSON or the wrong schema becomes 503 `unavailable`.
- Do not log the upstream body when validation fails.
- Reduce valid responses to the ADR's `BrowserView` fields only.
- Preserve source IDs and `cited`; never invent snippets or titles.
- Drop `run_id`, `approval_request`, and guard `detail`.
- Hide API `text` for `pending_approval` and `not_generated`, using fixed UI copy.

If adding a validation library, explain why it earns the dependency, update the one lockfile, and test it. A carefully tested manual type guard is also acceptable. Do not create a TypeScript interface and mistake compile-time typing for runtime validation.

### Transport mapping

Implement the ADR mapping exactly:

| Outcome | BFF HTTP | Browser state |
|---|---:|---|
| valid six-status `QueryResponse` | 200 | same six states |
| bad browser/API input | 422 | `invalid_question` |
| body >2 KB | 413 | `invalid_question` |
| upstream or local quota 429 | 429 | `busy` |
| upstream timeout | 504 | `timed_out` |
| kill switch, network failure, upstream 401/500/other, malformed 200, missing config | 503 | `unavailable` |

Accept `Retry-After` only when it is a non-negative whole number of seconds. Drop date-form and malformed values without crashing.

### Route-handler tests

Port the Python contract probe's behavior into real TypeScript route/unit/integration tests. At minimum cover all nineteen scenarios and the two contract checks:

- preset exact text;
- edited preset becomes free text;
- Q091 text remains free text;
- model declined;
- evidence gap;
- prompt injection blocked;
- forced pending approval fails closed;
- browser role/escalation rejected;
- overlong question;
- oversized raw body with whitespace padding;
- malformed JSON;
- upstream 429;
- timeout;
- connection failure;
- upstream 500;
- cut-off JSON;
- wrong response shape;
- date-form `Retry-After`;
- demo/kill switch off;
- presets are Internal-only and never pause;
- every UI state is exercised.

Add mutation checks for the security-critical assertions: remove fixed role, forward `approval_request`, accept an extra key, skip runtime response validation, or expose the service-token name/value. Each mutation must make a test fail.

## Block 3 — build the smallest chat Client Component

Replace the static explanation with an honest interactive slice without moving the whole case-study page across the client boundary.

### Component boundary

- `/procurerag/page.tsx` remains a Server Component.
- The chat form/history is one leaf Client Component.
- Preset data and public response types may live in neutral modules that import no server secret.
- Server-only modules must never be reachable from the client import graph.

### UI contract

- A labeled text area with visible 500-character limit/count.
- Four exact preset buttons: Q001, Q005, Q021, Q090.
- One submit action, disabled while a request is pending.
- No role selector and no approval controls.
- One visible state treatment per result state.
- Sources as IDs with a cited/not-cited marker.
- Page-local history only; a clear statement that requests are independent and not remembered by the model.
- Synthetic-data and third-party-provider disclosure.
- "Do not enter personal or confidential information."
- A stable live region for pending/result/error status; do not announce every keystroke.
- Focus moves intentionally after submit or error; no focus trap.
- Abort after 105 seconds so the BFF's 75-second typed timeout should normally win.
- No automatic retry.

### Status/warm-up route

If implementing the ADR's `GET /api/chat/status` today:

- it calls only FastAPI `/health`;
- it holds no browser-visible credential;
- it has a 90-second upstream timeout and 100-second `maxDuration`;
- it says "Waking the service (about a minute)" without claiming the model is ready before `/health` responds;
- it does not poll repeatedly or keep a deployment warm indefinitely;
- its future quota dependency is explicitly carried to Day 29.

If deferred, record the reason and make the local chat usable without pretending cold-start UX is solved.

### Accessibility and behavior checks

- keyboard-only path through presets, text area, submit, history, sources, and case-study links;
- visible focus and minimum target sizes;
- errors associated with the input;
- `aria-live` behavior observed, not just linted;
- 320, 375, 768, 1024, 1280, and 1440 px no-overflow checks;
- 400% zoom manual pass;
- screen-reader pass for form name, status, result, and sources;
- no-JavaScript: the case study remains present and the demo explains that interaction needs JavaScript;
- reduced motion;
- browser console and failed-network inspection.

## Block 4 — prove the local chain over real HTTP

### No-provider first

Start the FastAPI server with:

- a generated local service token supplied out of band;
- live LLM explicitly off;
- tracing explicitly off;
- cached/offline model settings where available.

Start the portfolio production build with the API URL and matching token supplied as server-only runtime environment variables.

Prove:

1. `/health` works without auth.
2. Direct `/query` and `/query/stream` without auth return 401.
3. Direct authenticated `/query` with Q001 returns the real `not_generated` path when the LLM is off.
4. Browser → `/api/chat` → FastAPI returns the same typed state.
5. Browser-supplied role/decision/query id never crosses the BFF.
6. No provider request or trace upload occurred.
7. The credential is absent from HTML, browser JavaScript, source maps, console, network response bodies, screenshots, and logs.

Record commands, ports, process ids only if useful, HTTP statuses, response states, and timings. Never record token values.

### Optional fake-LLM proof

A fake provider behind the real FastAPI process may prove the `answered` and `model_declined` UI without spend. Label it **fake/integration**, never live-answer evidence.

### Paid smoke gate

Do not make a paid call merely to finish Day 28. A paid smoke requires all of the following first:

- model and exact endpoint selected;
- current pricing source captured;
- maximum prompt/context assumption stated;
- public `max_tokens` cap implemented;
- worst-case cost calculated;
- daily cap derived from US$5/month;
- dedicated key limit set to US$5 and verified without exposing the key;
- training/provider-retention settings recorded;
- Juan explicitly approves the call.

If any item is open, record `paid smoke: blocked by <item>` and close Day 28 on the no-paid local vertical slice.

## Block 5 — economics and Day 29 handoff

Complete this worksheet with current numbers and a calculator, not mental arithmetic.

```text
model id:
provider endpoint:
pricing source URL and checked-at time:
input price per 1M tokens:
output price per 1M tokens:
maximum input/context tokens charged per public request:
public maximum output tokens:
worst-case input cost:
worst-case output cost:
worst-case total cost/request:
US$5 monthly ceiling / 30:
global daily request cap = floor(daily budget / worst-case cost/request):
OpenRouter key limit: US$5, verified yes/no:
provider training/logging/retention setting:
```

Then write the Day 29 handoff:

- persistent atomic admission store and exact provider;
- Lua/EVAL availability;
- global and per-client counters;
- in-flight lease TTL re-derived from measured continuation time;
- runtime kill-switch location;
- Azure subscription status and worst-case 24/7 compute cost;
- Vercel Hobby account/terms/`dub1` decision;
- deployed smoke set and rollback;
- provider disclosure text.

---

## Required evidence table

Fill every row with a result, a failure, or an explicit blocker.

| Evidence | Command/check | Result |
|---|---|---|
| ProcureRAG branch/base/divergence | `git status`, `git rev-parse`, `git rev-list` | pending |
| Portfolio branch/base/divergence | same | pending |
| Service-token negative tests | focused pytest selection | pending |
| Full ProcureRAG tests | `pytest -q` | pending |
| ProcureRAG compile/lint | `compileall`, Ruff | pending |
| Frozen/current retrieval | both regression modes | pending |
| Graph contracts | `src/graph_regression.py` | pending |
| Updated no-paid contract probe | script exit and scenarios | pending |
| Portfolio locked install/audit | `npm ci` | pending |
| Portfolio typecheck/lint | scripts | pending |
| Portfolio production build | `npm run build` | pending |
| TypeScript BFF contract tests | focused suite | pending |
| Full browser tests | `npm test` | pending |
| Runtime secret scan | built browser assets/source maps | pending |
| Local unauthenticated direct API | `/query`, `/query/stream` | pending |
| Local authenticated API, LLM off | `/query` | pending |
| Local browser→BFF→API | production build | pending |
| Console/network failures | Chromium production build | pending |
| Responsive/accessibility/no-JS | automated + manual | pending |
| Model/cost/output/daily cap | worksheet | pending |
| Provider key credit cap | account/API evidence, no secret | pending |
| Vercel terms/region | read-only decision record | pending |
| No deployment/public claim | repo/Pages/Vercel/Azure check | pending |
| `git diff --check` and clean-tree account | both repos | pending |

---

## Review questions Juan must be able to answer

Write concise answers in your own words before looking back at this route.

1. Why is the browser forbidden from calling FastAPI directly?
2. What does the service token authenticate, and what does it **not** authenticate?
3. Why is CORS irrelevant to the accepted same-origin browser path and insufficient as API authentication?
4. Why must authentication run before rate limiting and body validation?
5. Why use constant-time token comparison?
6. Why can the browser send only question text?
7. Why is a preset's `query_id` attached only on exact text equality?
8. Why are Q091 and Q092 withheld?
9. Why does a TypeScript interface not validate an upstream response at runtime?
10. Why are `run_id`, `approval_request`, guard details, and snippets removed?
11. Why do `gap_report`, `model_declined`, `blocked`, and `unavailable` need different UI states?
12. Why is `pending_approval` a fail-closed public state rather than an approval UI?
13. Why does the BFF stop reading at 2,049 bytes instead of trusting `Content-Length` or calling `request.json()`?
14. Why are there no automatic retries?
15. What exactly does the local real-HTTP smoke prove, and what does it not prove?
16. How do the 75 s upstream, 100 s function, and 105 s browser timeouts relate?
17. Why must worst-case cost use the public output cap and maximum permitted input/context instead of an average trace?
18. Why is an OpenRouter key limit still needed if a daily app quota is planned?
19. Which controls remain process-local or unbuilt after Day 28?
20. What must happen on Day 29 before the words "live demo" can become true?

---

## Day 28 close-out sequence

1. Complete the readings and applied-decision notes.
2. Implement and test service-token authentication in ProcureRAG.
3. Implement and test the typed BFF in the portfolio.
4. Build and test the smallest chat Client Component.
5. Run the local production chain over real HTTP with the LLM off first.
6. Complete the cost/provider/provisioning worksheet; do not make a paid call without approval.
7. Run all ProcureRAG and portfolio gates, including mutation and secret-boundary checks.
8. Record failures, confusing points, and what became clearer.
9. Give a three-minute walkthrough without notes.
10. Send this review prompt to Hermes:

> “Day 28’s guarded local chat slice is ready. Review both implementation branches against the accepted ADR and Day 28 route. Verify service-token ordering and constant-time comparison, unauthenticated health, fixed requester role, exact preset mapping, 2 KB raw-body cap, runtime response validation and reduction, all typed UI states, secret/client-bundle boundaries, no retries, real local HTTP integration, accessibility/no-JS behavior, model/cost/output/daily-cap evidence, and that no Day 29 deployment/quota/kill-switch work is falsely presented as complete. Juan owns implementation.”

11. Keep HER-296 In Progress until all required evidence is pushed and review findings are resolved.
12. Only then move HER-296 to Done and start Day 29.
