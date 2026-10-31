# Day 29 — Hosted portfolio demo: persistent quota, runtime control and deployed-chain proof

Date: 2026-10-27  
Linear: **HER-297** — Day 29 loop: host and harden the portfolio demo with spend controls  
Related gate: **HER-271** — Week 6 gate: live AI portfolio, ProcureRAG demo and readiness  
Prerequisite: **HER-296 / Day 28 is Done**

## Goal

Turn Day 28's secured local browser → Next.js BFF → FastAPI slice into one reviewable hosted demo path, without yet cutting the public portfolio URL over from GitHub Pages.

Day 29 is complete only when all of these claims have evidence:

1. the accepted ProcureRAG service is hosted on Azure Container Apps from an immutable image digest;
2. the accepted Next.js portfolio is hosted on a Vercel deployment in `dub1`;
3. browser requests still cross only the same-origin BFF and the BFF still fixes the public role to `requester`;
4. a persistent, atomic admission control enforces 54 paid requests/day globally, 10/day per client, and at most 2 in-flight upstream calls;
5. the admission store fails closed and no refusal calls the provider;
6. a runtime kill switch is read on every request, works without a redeploy, and has a measured flip-to-effect time;
7. Azure and OpenRouter secrets are supplied only through their runtime secret mechanisms;
8. the deployed chain passes the approved launch smoke and records honest answer-quality findings, cold-start behavior, spend, logs and rollback handles;
9. the portfolio still says `Live demo: in progress` until Day 30 performs public cutover and canonical/legacy URL work.

A deployed URL, a green HTTP status or a pretty answer alone is not this day's gate. The gate is a bounded, reversible and evidenced hosted chain.

---

## Ownership and safety boundary

Juan owns every implementation and live-system decision, including:

- ProcureRAG Python, tests, workflow and Azure template changes;
- portfolio TypeScript, React, CSS, tests, dependencies and lockfile changes;
- Vercel, Azure, Redis-compatible storage and OpenRouter accounts/resources;
- every secret, deployment, paid call, budget and public enable/disable action.

Hermes may maintain this route, the learning-log scaffold, Linear status/evidence, reviews and the final quiz. Hermes must not implement `src/*.py`, `tests/test_*.py`, or the portfolio application.

### Hard stop conditions

Do not enable paid/public traffic if any one of these is unknown or false:

- the deployment key is dedicated to this demo, has a **US$5 limit with a monthly reset**, and `GET /api/v1/key` confirms the non-secret limit fields;
- the model is `openai/gpt-4o-mini`, Zero Data Retention is still available for an endpoint that supports strict structured output, and OpenRouter prompt logging is off;
- the public output cap is `PROCURERAG_MAX_ANSWER_TOKENS=800`;
- the atomic store has passed a real-provider concurrency/admission proof;
- the global cap is 54/day and every enabled deployment sharing the OpenRouter key shares that same global counter;
- store failure, missing trusted client address, missing secret or missing kill-switch state fails closed;
- Azure's current subscription/credit/spending-limit state and the current 24/7 one-replica price have been checked against the **US$10/month cloud ceiling**;
- Juan has explicitly approved the paid deployed smoke.

Never print or record a token, key, Redis URL/token, raw client IP, subscription/tenant/client id, private deployment URL, request text, answer text from an unreviewed log, or secret-bearing command.

---

## Scope

### In scope today

- persistent atomic quota/admission control at the BFF;
- one lease per in-flight request, with expiry and idempotent release;
- a runtime kill switch stored outside the build and read on every request;
- trusted Vercel client-address handling and irreversible per-client hashing;
- a bounded `/api/chat/status` warm-up route, or a written evidence-backed rejection;
- Vercel function region and runtime settings;
- Azure runtime secrets, public-model configuration, min/max replica bounds and budget evidence;
- one enabled hosted preview path, with every other preview failing closed;
- deployment, launch smoke, cold-start/timeout/lease measurement, log inspection and rollback rehearsal;
- documentation and content-truth updates that stop claiming an unhosted local-only slice once the hosted evidence exists.

### Explicitly out of scope

- switching `juanfpinzon.github.io` away from the legacy Jekyll site;
- canonical URL, share image, metadata URL, legacy redirect, CV/LinkedIn URL update or custom domain;
- remote MCP, uploads, procurement writes, a role picker, visitor accounts or public approval controls;
- repairing Q091, changing the recorded Q090 gap example, or silently presenting Q001 as fully correct;
- autoscaling above one Azure replica;
- logging prompts, answers, retrieved excerpts, raw IP addresses, secrets or traces;
- claiming load-test capacity, production SLOs, correctness or enterprise authentication.

Day 30 owns cutover and launch polish. A Day 29 Vercel deployment may be publicly reachable as infrastructure, but it is not yet the canonical public portfolio URL.

---

## Course and source checkpoint

There is no new Boot.dev chapter today. Day 29 is the Week 6 hosting/operations slice. Read the exact targets below before implementation and record one applied decision or rejection per source in the learning log.

1. **Accepted portfolio architecture ADR** — `docs/adr/portfolio-demo-architecture.md` in `juanfpinzon/juanfpinzon.github.io` - READ
   - read §§8.1–8.6, 9–11;
   - especially the lease-per-request design, timeout nesting, public-ingress residual risk, kill switch and launch smoke set.
2. **Azure Container Apps — Authentication and authorization** — <https://learn.microsoft.com/en-us/azure/container-apps/authentication> - READ
   - read `Considerations for using built-in authentication`;
   - decide why Easy Auth is applied or rejected when `/health` must stay anonymous and the BFF already has service authentication.
3. **Azure Container Apps — Manage secrets** — <https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets?tabs=azure-cli> - READ
   - read application-level secret scope, `secretref:`, revision/restart behavior and permissions that expose `listSecrets`;
   - decide how the deploy workflow updates/references secrets without putting values in a committed YAML or command output.
4. **Azure Container Apps — Billing** — <https://learn.microsoft.com/en-us/azure/container-apps/billing> - READ
   - read Consumption-plan resource/request meters, scale-to-zero and the current monthly free grants;
   - calculate current expected and worst-case monthly cost with the current price sheet/calculator rather than copying an old quote.
5. **Azure Cost Management — Create and manage budgets** — <https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets> - READ
   - read `Create a budget in the Azure portal` and alert timing;
   - record that a budget alerts but **does not stop resources or consumption**.
6. **Vercel Functions limits** — <https://vercel.com/docs/functions/limitations> - READ
   - verify duration, memory, bundle/body and region limits for the chosen plan;
   - confirm the existing 100 s function limit fits the current plan.
7. **Vercel function regions** — <https://vercel.com/docs/functions/configuring-functions/region> - READ
   - read project-level `regions`, the single-region Hobby constraint and region/data-source latency;
   - use `dub1`, and record whether it is set in `vercel.json` or the dashboard.
8. **Vercel request headers** — <https://vercel.com/docs/headers/request-headers> - READ
   - read `x-forwarded-for`, `x-vercel-forwarded-for` and proxy behavior;
   - use a Vercel-set client address, never an arbitrary browser field. Record the local-test limitation separately.
9. **Vercel Marketplace storage** — <https://vercel.com/docs/marketplace-storage> - READ
   - verify the selected Redis-compatible product, current plan/price, region, environment scoping and injected variables before provisioning.
10. **Upstash Redis `EVAL`** — <https://upstash.com/docs/redis/commands/scripting/eval> and <https://upstash.com/docs/redis/sdks/ts/commands/scripts/eval> - READ
    - confirm server-side Lua execution, declared `KEYS`, atomic read-decide-write behavior and the TypeScript client API;
    - keep the script short and pass the timestamp through `ARGV`.
11. **Day 28 evidence** — `docs/day-28-guarded-http-chat.md` and `docs/learning-log.md`, Day 28 §`Day 29 handoff` - READ
    - carry forward the exact model/cost/cap/privacy decisions and the known Q001/Q090/Q091 outcomes; do not recompute from stale assumptions.

### Source checkpoint

- [ ] Accepted ADR read; applied/rejected decisions recorded.
- [ ] Azure auth and secrets pages read; applied/rejected decisions recorded.
- [ ] Azure billing and budget pages read; current calculator evidence recorded.
- [ ] Vercel limits, region, headers and current Hobby terms read; decisions recorded.
- [ ] Selected Redis provider's current plan, region and `EVAL` support verified before provisioning.
- [ ] Day 28 model/cost/privacy handoff re-checked against current provider data.

---

## Starting truth — measured at kickoff

### Accepted repository heads

```text
ProcureRAG accepted branch/head: main @ a9fa7a8836d711a471ce7f5e7dd1b71c442b2e78
ProcureRAG accepted commit:       Merge pull request #15 from juanfpinzon/day-28
ProcureRAG kickoff branch:        day-29 from that exact main head
ProcureRAG divergence:            day-29...origin/main = 0/0
ProcureRAG working tree:          clean before this route

portfolio accepted branch/head:   0ct26-overhaul @ e72b52a4af202a630964a3c197fe1072d4724fb0
portfolio accepted Day 28 merge:  003556bd943c296b08578f64518bbbd00f83156d (PR #2)
portfolio later delta:            PR #3, CV wording/files only; no chat/BFF drift
portfolio audit clone:            clean, 0/0 against origin/0ct26-overhaul
legacy Pages branch/head:         master @ 7526f0c39ba08a41c2a3d4aa4338365481d6028c (untouched)
```

GitHub state at kickoff:

- ProcureRAG PR #15: merged, all six required checks passed.
- Portfolio PR #2: merged into `0ct26-overhaul`; no workflow checks are configured.
- The portfolio repository remains public and its default branch remains `master`.

### Tool/account posture

```text
Python:       3.11.15
uv:           0.11.11
Node:         22.22.2
npm:          10.9.7
Azure CLI:    2.91.0; current session reports one Enabled default subscription
Vercel CLI:   65.4.0; logged out at kickoff
GitHub CLI:   authenticated
```

An enabled Azure CLI session is not evidence of remaining credit, a spending limit, resource existence, cost or deployment readiness. Vercel is not linked and nothing was deployed during kickoff.

### Clean baseline gates

ProcureRAG, with provider calls/tracing disabled:

```text
uv sync --locked --dev:                        exit 0, 154 resolved / 146 checked
uv lock --check:                               exit 0
pytest -q:                                     exit 0, 486 passed in 11.46 s
compileall src tests scripts:                  exit 0
ruff check src tests scripts:                  exit 0, All checks passed!
frozen fixture regression:                    exit 0, 7/7 as expected
current retrieval verification (offline):     exit 0, 6/6 [OK]
graph regression (offline):                   exit 0, 6/6 passed, 4 stand-in LLM calls
portfolio contract probe:                     exit 0, 20/20 scenarios + 2 checks
git diff --check:                             exit 0
```

Portfolio, fresh clone of `origin/0ct26-overhaul`:

```text
npm ci:                exit 0, 354 packages, 0 vulnerabilities
npm audit --omit=dev:  exit 0, 0 vulnerabilities
typecheck:             exit 0
lint:                  exit 0
production build:      exit 0; /api/chat is dynamic, content pages are static
Playwright:            exit 0, 139 passed in 38.3 s
git diff --check:      exit 0
```

No live provider call, trace upload, Azure mutation, Vercel link/deploy or Redis provisioning ran during kickoff.

### Current implementation truth

Already built and accepted:

- FastAPI service-token authentication before the body is read; `/health` remains open.
- public output-cap setting `PROCURERAG_MAX_ANSWER_TOKENS`.
- same-origin `/api/chat` BFF, fixed `requester`, exact preset mapping, 2 KB raw body cap, runtime upstream validation/reduction and no retries.
- ten typed UI states, accessible chat island, disclosure and a real local HTTP proof.
- model/cost decision: `openai/gpt-4o-mini`, ZDR, cap 800, worst-case US$0.0030525/request and 54/day.

Still missing:

- persistent quota/admission, client hashing, leases and runtime kill-switch storage;
- status/warm-up route;
- Azure token/model/key secret references and live configuration;
- Vercel account link, `dub1`, server-only settings and deployment;
- dedicated deployment OpenRouter key;
- deployed-chain smoke, cold-start/lease measurement and rollback proof.

The current Azure template intentionally has `PROCURERAG_LIVE_LLM=0` and no secrets. Because the accepted API now requires `PROCURERAG_SERVICE_TOKEN`, deploying that template unchanged fails closed at startup. The current portfolio route has `const DEMO_ENABLED = true`, not an operational kill switch.

---

## Invariants to preserve

1. Browser request is exactly `{question}`; role, `query_id` and `decision` never come from the browser.
2. BFF always sends `role: "requester"`; exact approved presets alone get an id.
3. No public approval path. `pending_approval` remains fail closed.
4. One browser action makes at most one upstream query; there is no automatic retry.
5. Invalid input is rejected before quota admission. A quota refusal or store failure makes zero upstream calls.
6. A successful admission charges both daily counters once. Upstream failure does not refund them.
7. An in-flight lease is removed only after a completed upstream response or definitive connection error. Timeout/disconnect/process death leaves it to expire.
8. `busy` means an enforced capacity/quota refusal. A broken/missing store or configuration is `unavailable`.
9. Raw IPs, questions, answers, retrieved excerpts and secrets are never stored in Redis or logs.
10. A kill switch stops new upstream work; it does not claim to cancel work already admitted.
11. Preview and production must not each get an independent 54/day budget while sharing one provider key.
12. Legacy `master`/GitHub Pages is untouched.

---

## Block 0 — human account and economics gate

Before code or provisioning:

- [ ] Juan reconfirms Vercel Hobby's current personal/non-commercial fit.
- [ ] Juan chooses the Vercel team/account and confirms `dub1` is available.
- [ ] Juan records Azure subscription offer, remaining credit, trial expiry and spending-limit state without recording identifiers.
- [ ] Use the current Azure calculator for 1 vCPU / 2 GiB Consumption in the chosen region:
  - normal scale-to-zero estimate;
  - worst case: one replica active for 720 hours;
  - registry, Log Analytics and request costs included where applicable.
- [ ] Compare worst case with the US$10/month cloud ceiling and define alert thresholds/action owner.
- [ ] Record explicitly: Azure budgets alert on delayed cost data; they do not stop the app.
- [ ] Create/choose one Redis-compatible store and record current plan, price, free allowance, region, eviction/persistence behavior and `EVAL` support.
- [ ] Create one dedicated OpenRouter deployment key with a US$5 monthly-reset limit; verify only `limit`, `limit_remaining` and `limit_reset`.
- [ ] Confirm account-wide prompt logging is off and the selected ZDR endpoint still supports strict structured output.
- [ ] Generate service/quota secrets outside both repositories; record only names/locations/rotation procedure.

For the 1 vCPU / 2 GiB template, a 30-day always-running replica consumes 2,592,000 vCPU-seconds and 5,184,000 GiB-seconds. Against the currently documented monthly free grants, 2,412,000 vCPU-seconds and 4,824,000 GiB-seconds remain billable before applying the current regional rates. This is a usage bound, not a price quote.

**Stop:** if the store, dedicated key, cloud ceiling or terms are not approved, Day 29 may still complete local implementation and tests, but it must not enable/deploy paid chat or claim the hosted gate.

---

## Block 1 — persistent atomic admission in the portfolio

Suggested branch: create `day-29-hosting` from accepted `0ct26-overhaul` @ `e72b52a` after `git fetch` proves 0/0 divergence.

Suggested boundaries (names may change, responsibilities may not):

- `lib/chat/admission.ts`: provider-neutral admission/release interface, key construction, UTC-day window and typed outcomes;
- `lib/chat/upstash-admission.ts`: Redis client and Lua execution; server-only;
- `lib/chat/admission.lua` or an exported literal: the reviewed atomic script;
- `tests/chat-admission.spec.ts`: deterministic unit/mutation tests;
- a provider integration test/script that uses an isolated namespace and deletes only its own keys.

### Key and privacy contract

- [ ] Namespace every key by app/environment and provider-key budget domain.
- [ ] All enabled deployments that share one OpenRouter key share the global daily key.
- [ ] Client key = HMAC-SHA-256 of the Vercel-set client IP with a server-only rotation secret; store only the digest.
- [ ] Production trusts `x-vercel-forwarded-for` (or the exact documented equivalent). A missing/ambiguous value fails closed.
- [ ] Local tests may inject an address through dependencies, but must not claim a locally supplied header is trustworthy.
- [ ] Daily bucket is defined in UTC and key expiry is bounded; record reset semantics in the UI/`Retry-After` behavior.
- [ ] No raw IP, question, answer, body, source text or secret enters a key, value, metric or log.

### One-script admission contract

Inputs: current epoch milliseconds, lease id, lease expiry, global cap 54, client cap 10 and in-flight cap 2. All keys touched by the script are declared through `KEYS`.

The script must atomically:

1. remove expired members from the in-flight sorted set;
2. read the current in-flight count and both daily counters;
3. return a typed refusal without changing anything if any cap is reached;
4. otherwise add exactly one lease and increment both counters;
5. set/retain bounded counter expiry;
6. return the admitted lease plus safe counter metadata for logs (never an address or hash).

Release is `ZREM` by this request's random lease id and is idempotent.

### Handler order

```text
runtime kill switch/config/store available?
  -> declared JSON?
  -> raw body <= 2 KB?
  -> exactly {question: 1..500 chars}?
  -> derive preset/free_text and trusted client digest
  -> one atomic admission
  -> exactly one upstream call
  -> release only on completed response or definitive network error
  -> map/validate/reduce response as on Day 28
```

Keep the existing timeout rule: a BFF timeout does not prove Azure/provider work stopped, so it does not release the lease.

### Required tests

- [ ] Global request 55 is refused after 54 admissions; no counter/lease changes on refusal.
- [ ] Client request 11 is refused after 10 while another client can still enter.
- [ ] Parallel admissions against an empty store admit exactly 2 at the in-flight cap.
- [ ] A release frees only its own lease; double/late release is harmless.
- [ ] An expired lease is pruned before counting.
- [ ] A timeout leaves its lease; a definitive pre-response network error releases it.
- [ ] Store unavailable/malformed reply/missing trusted address fails closed, logs no sensitive value and calls no upstream.
- [ ] Invalid browser bodies consume no counters and create no lease.
- [ ] Daily attempts are not refunded after upstream 401/422/429/500 or malformed 200.
- [ ] UTC reset/expiry boundary is deterministic under an injected clock.
- [ ] A real-store integration race test proves the Lua semantics; faking `eval()` alone is insufficient evidence of atomicity.
- [ ] Mutation checks catch non-atomic counter updates, refund-on-failure, release-on-timeout, raw-IP keys and a store-failure fail-open.

---

## Block 2 — runtime kill switch and bounded status route

### Kill switch

Use the same persistent control plane unless a better reviewed option is chosen.

- [ ] Key is read on every `/api/chat` and `/api/chat/status` request; missing/invalid/store failure means disabled.
- [ ] It is not a build-time environment variable and changing it requires no deployment.
- [ ] `off` answers 503 `unavailable`, makes zero Azure/provider calls and creates no paid admission.
- [ ] The operation is owner-only (Juan), documented as exact dashboard/CLI steps without storing a credential in the repo.
- [ ] Measure request-before-flip and first-request-after-flip timestamps; record flip-to-effect.
- [ ] Document that already admitted work may finish and that the secondary stop is Azure ingress/max replicas, followed by provider-key revocation.

### `/api/chat/status`

Preferred: implement the ADR warm-on-intent design.

- browser opens/intersects the demo → one same-origin status request;
- BFF calls unauthenticated Azure `/health`, never `/query`;
- upstream timeout 90 s; function `maxDuration` 100 s;
- typed `ready`/`waking`/`unavailable` response with `Cache-Control: no-store`;
- its own persistent global and per-client daily limits derived from the cloud ceiling, not the paid 54/day LLM counter;
- no polling loop and no automatic retry.

If rejected, record why and prove the chat's first cold request/timeout copy remains honest. Do not silently omit it.

Required tests cover store failure, kill-switch off, missing config, bounded status quota, upstream ready, timeout, unavailable, no secret/body forwarding and no repeated browser polling.

---

## Block 3 — Azure deployment configuration

Preserve the existing immutable-image and protected-environment workflow. The Day 29 change is runtime configuration, not a bypass around those gates.

### Secret/config contract

Container App secrets:

- `procurerag-service-token` → `PROCURERAG_SERVICE_TOKEN` by `secretRef`;
- `openrouter-api-key` → `OPENROUTER_API_KEY` by `secretRef`.

Plain revision settings:

- `PROCURERAG_LIVE_LLM=1` only in the explicitly approved live revision;
- `OPENROUTER_MODEL=openai/gpt-4o-mini`;
- `PROCURERAG_MAX_ANSWER_TOKENS=800`;
- `LANGSMITH_TRACING=false`;
- `LANGSMITH_TRACING_V2=false`;
- `HF_HUB_OFFLINE=1`;
- `OMP_NUM_THREADS=1`.

Scale remains `minReplicas: 0`, `maxReplicas: 1`, with 1 vCPU / 2 GiB and the accepted probes.

### Workflow requirements

- [ ] Secret values never enter committed YAML, image layers, output, step summaries or process arguments that logs display.
- [ ] Inspect Azure's secret permissions; do not casually grant a role whose wildcard includes `listSecrets`.
- [ ] Update existing app-level secrets through a masked environment and reference stable secret names from the revision template.
- [ ] URL-mode `container_smoke.py` receives the service token through its environment and masks the endpoint; it never prints either.
- [ ] Deploy still starts only on `main`, requires CI on the exact commit, requires the `production` environment reviewer, uses OIDC, deploys by digest and records the previous digest/revision.
- [ ] Stage deterministic authentication/health proof before the approved paid launch smoke if that reduces risk.
- [ ] Easy Auth decision recorded. Recommended default: reject it for this slice because requiring it for all requests conflicts with anonymous `/health`, while the application already authenticates both query paths before body parsing. This is not a claim that a shared token is enterprise identity.
- [ ] Read back only safe deployment properties: image digest, revision, health/running state, scale, non-secret env names, ingress HTTPS/`allowInsecure=false` and Log Analytics retention.

Direct public calls without the token must return 401 and make zero retrieval/provider calls. Any public request can still wake a scaled-to-zero app before application auth runs; record this residual compute-cost risk.

---

## Block 4 — Vercel deployment configuration

- [ ] Link the correct personal Vercel account/project only after Juan reconfirms terms.
- [ ] Configure `dub1` and verify the deployed function reports/runs there without recording visitor location.
- [ ] Set server-only `PROCURERAG_API_URL`, `PROCURERAG_SERVICE_TOKEN`, Redis credentials and client-hash secret; no `NEXT_PUBLIC_` prefix.
- [ ] Scope secrets/store to the one enabled environment. Other previews fail closed or have the kill switch off.
- [ ] Keep `PROCURERAG_API_URL` HTTPS.
- [ ] Build and inspect browser artifacts again for secret names/key-shaped values/API URL.
- [ ] Verify `/api/chat` and `/api/chat/status` are dynamic Node.js functions with the intended duration.
- [ ] Verify static pages remain readable when either function/store/Azure is down.
- [ ] Keep `master`/Pages untouched and do not add canonical production metadata yet.

Do not put the Azure endpoint, Redis URL or any token in a client component, browser bundle, public config, test fixture or screenshot.

---

## Block 5 — deployed proof and lease-TTL decision

### Free proof first

With the kill switch off or live LLM disabled as appropriate:

- [ ] Vercel content pages load and remain usable.
- [ ] status route behavior is typed and bounded.
- [ ] direct Azure `/health` is 200 without auth.
- [ ] direct Azure `/query` and `/query/stream` without/wrong auth are 401 before body work.
- [ ] missing/broken Redis produces `unavailable` and zero upstream calls.
- [ ] kill switch produces `unavailable` and zero upstream calls.
- [ ] quota and in-flight refusal produce `busy` and zero upstream calls.

### Paid launch smoke

Run only after Juan approves the spend and the dedicated key's limit/reset is verified. Use `scripts/chat_smoke.py <Vercel deployment>` one question at a time, no retry:

1. Q001 preset — expect `answered`; review wording manually because its Day 28 answer was only partly correct.
2. Q005 preset — expect `answered` and complete three-document procedure.
3. Q021 preset — expect `answered` and correct compliance rule.
4. Q090 preset — expect the intentionally honest `gap_report`.
5. Q001 paraphrase — expect an answer plus the unchecked-evidence caveat; manual correctness review.
6. company-car question — expect `model_declined`.
7. prompt injection — expect `blocked` and no model call.
8. Q091 as free text — record the known red result; do not turn it into a launch claim.

Record state, latency, cited IDs, provider/model routing, token counts/cost and manual verdict. Never paste credentials or raw logs containing visitor text.

### Cold start and lease TTL

Measure from admission through:

- Vercel BFF start;
- Azure scale-from-zero and health readiness;
- retrieval + provider call or provider timeout;
- BFF response/timeout and cleanup.

Derive the lease TTL from the worst measured continuation after admission plus a written safety margin. It must cover work that may continue after Vercel's 75 s fetch timeout or function termination, not merely exceed `maxDuration=100`. Keep 180 s only if the evidence supports it; otherwise change it and the tests/ADR together.

### Log/privacy proof

Inspect Vercel, Azure and provider evidence for:

- one safe BFF line per request: route/state/status/latency/preset-or-free-text/quota counters;
- no question, answer, excerpt, raw IP/hash, token, API URL or Redis credential;
- tracing off and no LangSmith upload;
- platform retention recorded;
- browser responses/assets contain no server-only values.

---

## Block 6 — rollback rehearsal

Record exact handles before changing traffic:

- previous Azure revision and immutable image digest;
- new Azure revision and immutable image digest;
- current and previous Vercel deployment ids/URLs (mask private URLs in public evidence);
- kill-switch state and store namespace;
- provider key id/label and limit metadata, never the key.

Rehearse in this order:

1. turn the runtime kill switch off and prove new chat requests stop without taking down the portfolio;
2. roll Vercel back to the prior deployment and smoke content routes;
3. reactivate/deploy the previous Azure image digest and smoke `/health` plus authenticated retrieval-only behavior;
4. restore the new revision only if desired, then leave the kill switch in the intentionally recorded final state.

Do not rehearse by deleting resources or changing legacy Pages.

---

## Required verification

### ProcureRAG

Run with live calls/tracing forced off unless a step explicitly belongs to the approved smoke:

```text
uv sync --locked --dev
uv lock --check
pytest -q
python -m compileall -q src tests scripts
python -m ruff check src tests scripts
python src/regression_suite.py
HF_HUB_OFFLINE=1 python src/regression_suite.py --verify-retrieval
HF_HUB_OFFLINE=1 python src/graph_regression.py
python scripts/portfolio_contract_probe.py
python scripts/container_smoke.py <new-image>
git diff --check
```

Also require exact-commit CI, image-internal offline retrieval/graph gates and the post-deploy URL smoke.

### Portfolio

```text
npm ci
npm audit --omit=dev
npm run typecheck
npm run lint
npm run build
npm test
git diff --check
```

Add focused admission/store, status-route, kill-switch, secret-scan, deployment-region and deployed-browser tests. Record every command separately with exit code and meaningful output.

### Evidence table

| Evidence | Required result |
|---|---|
| Branch/base/divergence | exact accepted base and 0/0 before implementation in both repos |
| Full ProcureRAG deterministic gate | all tests/lint/regressions/probe green, no provider/tracing |
| Full portfolio gate | locked install/audit/typecheck/lint/build/browser suite green |
| Atomic store proof | parallel real-store admission respects all three caps; isolated keys cleaned |
| Fail-closed proof | store/config/address failures and kill switch call nothing upstream |
| Trusted client key | platform header present; only HMAC digest stored; no raw IP in logs/store |
| Azure secret boundary | secret refs only; no committed/logged values; protected routes return 401 without token |
| Vercel secret boundary | no server setting/value/API URL in HTML, JS, source maps or responses |
| Region and timeout | `dub1`; 75/90/100/105 s layers reconciled |
| Deployment integrity | CI-passed commit → tested image → registry digest → ready revision |
| Cost controls | 54 global/day, 10 client/day, 2 in-flight, US$5 key cap/reset, max 1 replica, budget alert and kill switch |
| Paid smoke | approved, one call per case, results/cost/manual verdict recorded |
| Cold-start/TTL | measured continuation and derived lease TTL recorded |
| Privacy/logging | ZDR still active, prompt logging off, tracing off, no sensitive payload logs |
| Rollback | chat kill switch plus Vercel/Azure rollback rehearsal passed |
| Claim truth | hosted evidence exists, but canonical/public cutover still explicitly Day 30 |

---

## Commit and review boundaries

Recommended small commits:

1. **Portfolio:** persistent admission abstraction, Lua script and deterministic tests.
2. **Portfolio:** integrate admission/release and runtime kill switch into `/api/chat`.
3. **Portfolio:** bounded `/api/chat/status`, UI warm-up state and tests.
4. **ProcureRAG:** Azure secret/config template and protected deploy-workflow changes.
5. **Both:** deployed-proof scripts/docs/content-truth updates and evidence.

After each commit, re-run the focused tests. Before push/PR, run each repository's full gate. Do not mix Day 30 cutover work into these commits.

---

## Learning-log evidence skeleton

The Day 29 log entry must record:

- source checkpoint and applied/rejected decisions;
- exact accepted heads and implementation branches;
- account/economics worksheet without identifiers/secrets;
- quota key schema, UTC reset and atomic-script explanation;
- real-store concurrency proof and mutation results;
- kill-switch location, owner and flip-to-effect measurement;
- status-route decision and limits;
- Azure/Vercel configuration evidence and secret boundary;
- every deterministic/full test command;
- deployed free proof, paid smoke (if approved), costs and manual answer verdicts;
- cold-start timings and lease-TTL derivation;
- logs/privacy inspection;
- rollback handles/rehearsal without exposing URLs/secrets;
- failures/confusions and corrected claims;
- interview answers, review questions and a timed walkthrough.

---

## Interview prompts

Answer these in your own words after implementation:

1. Why must global, client and in-flight checks happen in one atomic script?
2. Why is one expiring lease per request safer than one counter with a TTL?
3. Why is a timeout not grounds to release a lease or refund quota?
4. What makes a Vercel client-IP header trustworthy in deployment but not in a local unit test?
5. Why use an HMAC digest rather than store an IP or plain hash?
6. Why does store failure fail closed, and why is that `unavailable` rather than `busy`?
7. How do 54/day, 10/client/day, 2 in flight, the US$5 key cap and max 1 replica protect different failure modes?
8. Why does an Azure budget not count as a hard spending limit?
9. Why can an unauthenticated request still cost Azure compute even when FastAPI returns 401?
10. Why was Azure Easy Auth applied or rejected for this architecture?
11. What work can continue after the browser/BFF times out, and how did that set the lease TTL?
12. What does the kill switch stop, what does it not cancel, and how fast did it take effect?
13. Why must preview and production share a global counter if they share one model key?
14. What did the deployed smoke prove that Day 28's local real-HTTP proof did not?
15. Why are Q001, Q090 and Q091 still honest limitations after the demo is hosted?
16. How do you roll back the chat without taking the case study offline?
17. What evidence would justify changing the 54/day cap later?
18. Why is a hosted demo still not the Day 30 public launch?

---

## Three-minute walkthrough target

1. **Architecture (30 s):** browser → same-origin Vercel BFF → token-protected Azure API, with the Redis admission boundary before Azure.
2. **Spend controls (40 s):** atomic 54/day + 10/client/day + two leases, dedicated US$5 key, max one replica, budget alert and kill switch.
3. **Live proof (60 s):** one answerable preset, Q090's honest gap, an injection refusal, then flip the kill switch and show zero upstream work.
4. **Operations (30 s):** cold-start/lease timing, safe logs, digest deployment and rollback handles.
5. **Honest limits (20 s):** no visitor identity or public approval; Q001 wording and Q091 quality remain known issues; Day 30 still owns canonical cutover.

Target: under 3 minutes without reading this route.

---

## Juan implementation handoff

> Start from ProcureRAG `day-29` @ `a9fa7a8` and portfolio `0ct26-overhaul` @ `e72b52a`. Implement the accepted ADR's persistent atomic admission, runtime kill switch, bounded status route, Azure secret/live-model configuration and Vercel `dub1` deployment. Preserve the Day 28 browser/BFF/API contract and all honest-answer limits. Provision or spend only after completing Block 0, and run paid deployed smoke only after explicit approval. Record all non-secret evidence in the Day 29 learning-log section. Do not touch portfolio `master` or perform Day 30 cutover.

## Review prompt

> Review Day 29 across ProcureRAG and the portfolio against the accepted architecture ADR and `docs/day-29-hosted-portfolio-demo.md`. Verify atomic admission across global/client/in-flight caps; lease expiry/release semantics; fail-closed store, trusted-address and kill-switch paths; no quota refund or automatic retry; no raw IP/payload/secret storage or logs; one enabled budget domain across deployments; Azure secret refs and digest-gated deployment; Vercel `dub1` and server-only settings; status-route abuse bounds; exact spend controls; deployed smoke/manual answer verdicts; measured cold-start-derived lease TTL; rollback evidence; and that Day 30 cutover/public claims remain undone. Treat faked Redis calls, green HTTP alone, unverified provider-key limits, or missing live-chain evidence as insufficient. Juan owns implementation.
