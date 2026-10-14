# Day 21 — FastAPI Async/Streaming Serving Surface

Date: 2026-10-07 kickoff.

Linear: HER-289 — Day 21 loop: FastAPI async/streaming serving surface.

Related gate: HER-270 — Week 5 gate: serving, Azure, CI/CD, MCP.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

No new Boot.dev chapter today. Day 21 starts Week 5: turn the local ProcureRAG graph/guardrail pipeline into a small production-shaped HTTP service boundary.

Primary production-RAG source:

- **freeCodeCamp — `Production RAG with LangChain & Vector Databases`**: <https://www.freecodecamp.org/news/production-rag-with-langchain-vector-databases> - Completed full course.
  - `Production Hosting`. - Completed
  - `Production Project`. - Completed
  - `Set up the Security Layer` — reactivate only the entry-boundary/security-layer idea; Day 20 already built the local guardrails. - Completed
  - `Set up the LangGraph Agent and the FastAPI API - Testing and LangSmith Observability Dashboard`. - Completed
  - `Test the Security Layer` — use the idea of API-level security tests; keep ProcureRAG’s implementation local and deterministic. - Completed
  - `Security Checklist` — use as a serving-readiness checklist, not as a claim that Day 21 solves enterprise security. - Completed

FastAPI / serving docs:

- **FastAPI docs — `Server-Sent Events (SSE)`**: <https://fastapi.tiangolo.com/tutorial/server-sent-events>
  - `What Are Server-Sent Events?`
  - `Streaming SSE with FastAPI`.
  - `Return Type Annotations`.
  - `ServerSentEvent` for explicit `event` / `id` / `retry` fields when needed.
  - Note: this page says SSE support via `fastapi.sse.EventSourceResponse` was added in FastAPI `0.135.0`; if the installed version or lockfile path does not support it, use the fallback below.
- **FastAPI docs — `Custom Response - HTML, Stream, File, Others`**: <https://fastapi.tiangolo.com/advanced/custom-response/>
  - `StreamingResponse` / custom response behavior.
  - `response_class` vs returning a `Response` directly.
  - OpenAPI documentation caveat for custom responses.
- **FastAPI docs — `Testing` / `TestClient`**: use deterministic API tests instead of live provider calls.
- **Uvicorn / FastAPI server docs**: local startup should bind to `127.0.0.1` for development and later to `0.0.0.0` only inside Docker/Container Apps.

Week 5 preview sources, read lightly only for context today:

- **Microsoft Learn — `Deploy a Flask or FastAPI web app as a container in Azure Container Apps`**: <https://learn.microsoft.com/en-us/azure/developer/python/tutorial-containerize-simple-web-app>
  - Use only to understand why the API should expose `/health`, clear ports, and container-friendly startup. Day 22/23 own Docker/Azure.
- **Hugging Face MCP Course — Unit 1 `Introduction to Model Context Protocol (MCP)`** and Unit 3 `Advanced MCP Development: Building Custom Workflow Servers for Claude Code`.
  - Read only enough to see the future shape: Day 25 will expose a useful ProcureRAG capability as a tool/server. Day 21 should not jump to MCP yet.

## Day 21 objective

Expose ProcureRAG through a minimal FastAPI service that makes the application boundary explicit:

> “What does a caller send, what validation runs before retrieval, what roles/confidentiality rules are enforced at the boundary, what happens when the graph needs approval, and how can a UI or client stream progress without hiding safety decisions?”

By the end of Day 21, Juan should have a small service that can be started locally, tested without live LLM credentials, and explained as the first step from scripts toward a production-facing RAG product.

This is not a generic FastAPI tutorial app. It should wrap the real Week 4 artifacts:

- Day 16 recursive retrieval / evidence diagnosis.
- Day 17 graph routing.
- Day 18 approval gate / HITL control.
- Day 19 structured result / trace row vocabulary.
- Day 20 guardrail findings.

## Starting state

Current repo evidence at kickoff:

- `src/agent_guardrails.py` — guarded request path around the Day 19 graph, with input/context/action/output guard findings and no silent approval default.
- `src/agent_observability.py` — `AgentRunTrace`, `AgentResult`, structured generation, JSONL trace row read/write, and statuses such as `answered`, `gap_report`, `not_generated`, and `model_declined`.
- `src/agent_control_plane.py` — `interrupt()` approval gate, decision vocabulary (`approve`, `edit`, `reject`), and in-memory checkpointing.
- `src/agent_graph.py` / `src/agentic_retrieval.py` — route distribution and recursive retrieval policy: 76 direct `generate`, 2 `recursive_retrieve -> generate` (`Q091`, `Q092`), and 15 `report_gap` cases.
- `src/regression_suite.py` — frozen regression cases and current-retrieval verification.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query labeled source. Do not create `data/golden_queries.jsonl`.
- `pyproject.toml` currently does **not** list `fastapi`, `uvicorn`, or `httpx`; adding serving dependencies and lockfile changes is part of Juan’s implementation if he chooses real FastAPI today.

Day 20 caveats to carry forward into the API boundary:

- Graph-path answer quality is still unmeasured; a valid API response is not a correct answer.
- Retrieval ignores `confidentiality` labels; the API must at least accept a role/confidentiality contract and enforce or explicitly stub it.
- Trace rows may keep raw model text; the API must return user-safe text, not raw trace internals.
- No person has reviewed a live HITL request; Day 21 should return `pending_approval` instead of auto-approving.
- The service surface needs input-length, on-topic, role/confidentiality, and rate-limit boundaries.

Baseline checks at kickoff:

```bash
./.venv/bin/pytest -q
# 304 passed in 4.54s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# All cases match their currently expected state (frozen fixtures).
# The current retrieval pipeline still matches every case's expectation.
```

Git status at kickoff was clean on `main` before this Day 21 route/log scaffold was added.

## Key concepts to nail today

### The API boundary is where product policy starts

Until today, ProcureRAG has been mostly script-shaped: run a CLI, inspect output, write evidence. A production copilot needs a stable boundary between caller and system. That boundary is not just “POST a question.” It is where Juan decides:

- what request fields exist (`query`, caller role, optional query id, approval decision);
- what is rejected before retrieval (too long, off-topic, malformed, unsafe);
- what role/confidentiality policy is applied before chunks are returned to a model or user;
- what user-safe result shape is returned;
- what happens when the graph needs a human decision.

A good Day 21 answer should sound like: “The service does not make the RAG system smarter; it makes the contract explicit.”

### Async/streaming is useful only if it preserves state and safety

Streaming is not just token streaming. For this project, a useful stream can emit structured events such as:

1. `request_validated`;
2. `retrieval_started`;
3. `guard_finding`;
4. `approval_required`;
5. `gap_report`;
6. `answer_ready`.

If real SSE blocks, a deterministic generator/iterator tested by the API is enough for today. The point is that clients can see progress and safety decisions without scraping logs or waiting for one opaque final blob.

### `pending_approval` is a product state, not a failure

Day 18’s `interrupt()` was a graph-level control. Day 21 must translate it into an API-level response. A Q091/Q092-shaped case without a reviewer decision should not silently auto-approve and should not look like a server error. It should return an explicit, typed state such as `pending_approval`, with the safe request payload a reviewer would need.

This is the bridge from “agent can pause” to “a real user/product can handle the pause.”

### Authorization/confidentiality is different from PII regex redaction

Day 20 redacted emails, cards, and international phone numbers. That does not solve confidential-document access. If a caller role should not see `Confidential` documents, the API should model that policy explicitly.

Minimum acceptable Day 21 version: a role/confidentiality field in the request contract, a deterministic test that proves the service does not expose confidential chunks to a lower-privilege role, and honest docs if the underlying retrieval filter is still a stub.

### Service tests should be CI-safe

The default API tests should not call OpenRouter, LangSmith SaaS, Azure, or any paid provider. Use the same fake-client/deterministic style as Days 18–20. Live provider smoke can be optional and clearly marked later, but the Day 21 acceptance path is local.

## Target evidence by end of day

- [ ] Course/source work recorded with exact source section names:
  - [ ] freeCodeCamp `Production Hosting`.
  - [ ] freeCodeCamp `Production Project`.
  - [ ] freeCodeCamp `Set up the Security Layer`.
  - [ ] freeCodeCamp `Set up the LangGraph Agent and the FastAPI API - Testing and LangSmith Observability Dashboard`.
  - [ ] freeCodeCamp `Test the Security Layer`.
  - [ ] freeCodeCamp `Security Checklist`.
  - [ ] FastAPI `Server-Sent Events (SSE)` → `Streaming SSE with FastAPI`, `Return Type Annotations`, `ServerSentEvent`.
  - [ ] FastAPI `Custom Response - HTML, Stream, File, Others` → `StreamingResponse` / response-class caveats.
- [ ] Serving dependency decision recorded:
  - [ ] exact packages added, if any (`fastapi`, `uvicorn`, `httpx`, optional SSE dependency), and lockfile changed;
  - [ ] or exact blocker if dependency setup failed.
- [ ] API contract table exists in `docs/learning-log.md` or a small API doc:
  - [ ] endpoint;
  - [ ] request schema;
  - [ ] response schema;
  - [ ] status vocabulary;
  - [ ] CI-safe vs optional live behavior.
- [ ] Minimal routes exist and are tested:
  - [ ] `/health` returns service/version/readiness information without importing live provider credentials.
  - [ ] one non-streaming query endpoint returns a typed response.
  - [ ] one streaming/SSE endpoint or documented equivalent emits typed progress events.
- [ ] Entry protections are represented in tests:
  - [ ] too-long query blocked before retrieval;
  - [ ] off-topic/non-procurement query blocked or returns a typed refusal;
  - [ ] known PII is redacted or blocked using Day 20 behavior;
  - [ ] unauthorized role/confidentiality case does not expose confidential chunks;
  - [ ] Q091/Q092-shaped case returns `pending_approval` without a decision.
- [ ] Baseline gates pass: `pytest`, `compileall`, `ruff`, `regression_suite.py --verify-retrieval`.
- [ ] Local API smoke evidence exists:
  - [ ] startup command;
  - [ ] `/health` response;
  - [ ] one deterministic query response;
  - [ ] one streaming/SSE or event-iterator response;
  - [ ] no live provider needed for default proof.
- [ ] Known caveats are honest:
  - [ ] rate limiting is real or a stub;
  - [ ] approval persistence is in-memory or durable;
  - [ ] role/confidentiality filtering is real or a bounded prototype;
  - [ ] streaming is SSE or a fallback iterator;
  - [ ] answer quality remains a separate eval problem.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and choose the serving contract, 30–45m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
./.venv/bin/python src/agent_guardrails.py
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_guardrails.py --all-queries
```

Then sketch the API contract before coding:

| Endpoint | Purpose | Request | Response | CI-safe proof |
|---|---|---|---|---|
| `GET /health` | service readiness | none | app/version/status | TestClient |
| `POST /query` | non-streaming answer/gap/pending approval | query + role + optional decision | typed result | fake client |
| `GET/POST /query/stream` or equivalent | progress stream | same core fields | typed events | iterator/SSE test |
| optional `POST /approvals/{id}` | future resume path | reviewer decision | resumed result | may be deferred |

Recommended status vocabulary:

- `answered`
- `gap_report`
- `not_generated`
- `model_declined`
- `blocked`
- `pending_approval`
- `error` only for real server/application failures, not normal RAG uncertainty

### Block 1 — Course/source work, 75–105m

Read/map the sources with ProcureRAG notes:

1. freeCodeCamp production RAG:
   - `Production Hosting` — what changes when a RAG app is served over HTTP.
   - `Production Project` — service layout, not copy-pasted code.
   - `Set up the Security Layer` — map to Day 20 guardrails and today’s API entry checks.
   - `Set up the LangGraph Agent and the FastAPI API - Testing and LangSmith Observability Dashboard` — identify which parts apply to ProcureRAG’s `StateGraph` / guardrail wrapper.
   - `Test the Security Layer` and `Security Checklist` — translate into endpoint tests.
2. FastAPI SSE docs:
   - When to use SSE vs a normal JSON response.
   - Why typed return annotations matter for streaming items.
   - Whether `EventSourceResponse` is available in the dependency version Juan installs.
3. FastAPI custom response docs:
   - When `StreamingResponse` is sufficient.
   - OpenAPI documentation caveat when returning raw `Response` objects.

Scratch-note prompts:

- Which endpoint should own HITL: `/query` returning `pending_approval`, a separate approval endpoint, or both?
- What exactly does a buyer role mean today?
- Which data is safe for a response body vs trace/audit only?
- Which parts must not call a live LLM in tests?

### Block 2 — Design the Pydantic contracts, 45–60m

Before coding, write the request/response/event shapes in prose or a small docs table.

Suggested concepts for Juan to design himself:

- `QueryRequest`: `query`, optional `query_id`, caller role / authorization context, optional reviewer decision, optional streaming flag.
- `QueryResponse`: status, user-safe text, citations/sources, guard findings, approval request if pending, trace handle or run id, caveats.
- `StreamEvent`: event type, sequence number, user-safe payload, optional run id.
- `HealthResponse`: app name/version, dependency mode, live-provider availability should be false/omitted unless intentionally checked.

Keep this contract small. The goal is a service boundary Juan can explain, not a sprawling product API.

### Block 3A — Primary route: Juan-owned FastAPI artifact, 120–150m

Possible artifact shape, for Juan to design and implement:

- A small API module, likely `src/api.py` or equivalent.
- Pydantic request/response/event models near the API or in a tiny boundary module.
- Dependency injection seams so tests can swap the real guarded pipeline for fakes.
- Tests such as `tests/test_api.py` that use `TestClient` or an async client.
- A local startup command using Uvicorn.

Suggested minimum behavior:

1. `/health` returns without initializing live model clients.
2. `POST /query` validates input length and procurement scope before running retrieval.
3. The API calls the guarded pipeline, not raw generation, for the normal query path.
4. If the graph would need approval and no decision is supplied, the API returns `pending_approval`, not `answered`, `gap_report`, or a 500.
5. The user-visible response uses `GuardedResponse.text` / user-safe data, not raw unredacted trace internals.
6. The role/confidentiality field has at least one deterministic test that proves the intended behavior or exposes the stub honestly.
7. Streaming emits typed events and can be tested without live providers.

Recommended implementation constraints:

- Keep default tests local and credential-free.
- Do not introduce an actual hosted server requirement for tests.
- Avoid a full frontend today.
- Avoid Docker/Azure today except as design notes; Day 22/23 own those.
- If using SSE is blocked by dependency/version issues, fall back to `StreamingResponse` or a tested event iterator and record the blocker.

### Block 3B — Fallback route: typed API contract + non-streaming service only, 60–90m

Use this if FastAPI/SSE setup blocks.

Still produce:

1. The Pydantic request/response/event contract.
2. `/health` and one typed non-streaming query endpoint.
3. Tests for too-long input, off-topic input, unauthorized/confidentiality behavior, and pending approval.
4. A documented streaming fallback: event iterator, `StreamingResponse`, or exact blocker.
5. Learning-log evidence with the exact failed command/error and next retry path.

This fallback is acceptable if the service boundary is real and tested. It is not acceptable to only watch the freeCodeCamp/FastAPI videos and skip a ProcureRAG-specific artifact.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/learning-log.md` — Day 21 entry with exact source completion, endpoint contract, verification output, API smoke evidence, caveats, and next step.
- Optional `docs/api-serving.md` or `docs/eval-report.md` addendum if the API contract needs a standalone artifact.

Then answer the interview drill below without notes.

## Interview drill

1. What is the difference between a script-shaped RAG demo and a service boundary?

   **Expected answer shape:** A script is an operator-only path: run command, inspect logs. A service boundary defines request schema, validation, authorization context, result status, errors, and safe user-visible payloads. The boundary is where product policy lives.

2. Why should Q091/Q092 return `pending_approval` instead of auto-approving?

   **Expected answer shape:** Day 18’s approval gate protects the second retrieval action. If an API silently approves, it removes the human control. `pending_approval` makes the pause visible to the client and lets a real reviewer decide. Auto-approval is acceptable only when labeled as demo/test evidence, not production behavior.

3. What should stream events represent in ProcureRAG?

   **Expected answer shape:** Not only token chunks. Useful events are request validation, retrieval start/end, guard findings, approval required, gap report, and answer ready. Each event should be typed and safe to show.

4. Why is role/confidentiality enforcement not the same as PII redaction?

   **Expected answer shape:** PII redaction detects data patterns like emails/phones/cards. Authorization decides whether this caller can see a document or chunk at all. A confidential policy can have no PII but still be unauthorized.

5. What belongs in CI-safe API tests vs optional live smoke?

   **Expected answer shape:** CI-safe tests use fake clients and deterministic retrieval to verify schemas, validation, guard behavior, pending approval, and streaming event structure. Optional live smoke may call a provider or LangSmith, but it must be opt-in, bounded, and documented.

6. How does FastAPI’s response model help a RAG service?

   **Expected answer shape:** It makes the API contract machine-checkable and documented in OpenAPI. Clients can rely on fields like `status`, `text`, `citations`, and `approval_request` instead of scraping prose. It complements, not replaces, internal Pydantic trace/result models.

7. What must be true before Day 21 is review-ready?

   **Expected answer shape:** The local API starts, `/health` works, normal and streaming/equivalent query paths are tested, entry guards are represented, Q091/Q092-shaped approval does not silently run, baseline gates pass, and docs record exact source work plus caveats.

## Hermes review protocol

When Juan has a serious Day 21 pass ready, ask Hermes:

> Day 21 FastAPI serving surface done. Review HER-289: exact freeCodeCamp/FastAPI source sections, API request/response/event contracts, `/health`, non-streaming query, streaming/SSE or fallback behavior, input-length/on-topic/role-confidentiality protections, Q091/Q092 pending-approval behavior, tests, local API smoke evidence, `docs/learning-log.md` evidence, and real verification outputs. Run pytest/compile/ruff/regression and the API smoke commands. Do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, run gates, verify the acceptance criteria, quiz Juan on the drill, and either close HER-289 or return precise remaining tasks. Hermes must not replace Juan’s implementation.

## Stop condition

Day 21 is complete when:

1. The named freeCodeCamp and FastAPI sections have been completed or explicitly summarized.
2. A minimal FastAPI or documented equivalent service exists around the ProcureRAG guarded graph path.
3. `/health`, one non-streaming query route, and one streaming/SSE or event-iterator path are tested.
4. Input-length, on-topic, role/confidentiality, and approval-boundary behaviors are represented by deterministic tests or honest blockers.
5. Q091/Q092-shaped cases cannot silently auto-approve through the API.
6. Baseline gates pass: `pytest`, `compileall`, `ruff`, and `regression_suite.py --verify-retrieval`.
7. The learning log contains real evidence and caveats, not placeholders.
8. Juan can explain the service lifecycle from request validation through retrieval, guardrails, HITL, generation, response, and streaming.

Do not close HER-289 on route creation alone. The route is the kickoff; Juan’s source work, artifact, evidence, and explanation are the acceptance criteria.
