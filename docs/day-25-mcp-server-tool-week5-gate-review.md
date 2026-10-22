# Day 25 — MCP Server/Tool and Week 5 Gate Review

Date: 2026-10-22 kickoff.

Linear: HER-293 — Day 25 loop: MCP server/tool + Week 5 gate review.

Related gate: HER-270 — Week 5 gate: serving, Azure, CI/CD, MCP.

Project rule: Juan owns the MCP dependency choice, server/tool implementation, tests, Inspector/client evidence, and any change under `src/`, `tests/`, `scripts/`, `pyproject.toml`, or `uv.lock`. Hermes may scaffold this route and the learning-log evidence fields, then review, quiz, and help debug after a serious attempt. Hermes does not write the implementation.

## Course target for today

**No new Boot.dev chapter today.** Day 25 is the Week 5 MCP integration and cumulative gate-review day. The goal is to understand the protocol well enough to expose one existing ProcureRAG capability safely—not to build a generic toy server or a second RAG pipeline.

Budget **105–135 minutes** for the required readings. Read the named pages/sections, then record one ProcureRAG-specific takeaway per source in `docs/learning-log.md`.

### Block A — MCP mental model, 30–40m 

1. **Hugging Face MCP Course — Unit 1 `Introduction to Model Context Protocol`** - READ

   <https://huggingface.co/learn/mcp-course/en/unit1/introduction>

   Read the exact introductory targets:
   - `What is Model Context Protocol?`
   - `Key Concepts`
   - `Integration Challenges`
   - `Benefits and Goals`
   - `Simple Example`

   ProcureRAG question: what M×N integration work disappears when Claude Code, an IDE, or another host can discover the same ProcureRAG server?

2. **Hugging Face MCP Course — Unit 1 `Key Concepts and Terminology`** - READ

   <https://huggingface.co/learn/mcp-course/en/unit1/key-concepts>

   Read:
   - `Host`
   - `Client`
   - `Server`
   - the capability table for `Tools`, `Resources`, `Prompts`, and `Sampling`

   ProcureRAG question: which component owns LLM reasoning, and which component should expose typed procurement capabilities without pretending to be the agent?

3. **Hugging Face MCP Course — Unit 1 `Architectural Components`** - READ

   <https://huggingface.co/learn/mcp-course/en/unit1/architectural-components>

   Read the full page, especially the seven-step flow from user interaction through capability discovery, invocation, execution, and result rendering.

4. **Hugging Face MCP Course — Unit 1 `The Communication Protocol`** - READ

   <https://huggingface.co/learn/mcp-course/en/unit1/communication-protocol>

   Read:
   - JSON-RPC requests, responses, and notifications;
   - initialization and capability negotiation;
   - discovery (`tools/list`, and the equivalent resource/prompt discovery);
   - execution (`tools/call`);
   - stdio versus HTTP/SSE/Streamable HTTP.

   ProcureRAG question: why is local stdio the smallest safe first transport for Day 25, while remote Streamable HTTP creates a separate authentication/network deployment problem?

5. **Hugging Face MCP Course — Unit 1 `Understanding MCP Capabilities`** - READ
 
   <https://huggingface.co/learn/mcp-course/en/unit1/capabilities>

   Read the control distinction among tools, resources, prompts, and sampling.

   ProcureRAG question: why is a retrieval/query operation a **tool**, a sanitized static gate summary potentially a **resource**, and a procurement-review workflow a **prompt**?

### Block B — official Python SDK, 45–55m

6. **Official MCP Python SDK — `Get started`** - READ

   <https://py.sdk.modelcontextprotocol.io/>

   The official docs observed at kickoff are the **v2** line (page header: v2.3.0) and require Python 3.11+, which matches this repo. Read:
   - `Installation`;
   - `First steps`;
   - `Connect to a real host`;
   - `Testing`.

   Version rule: do not mix a v1 `FastMCP` tutorial with v2 imports by accident. Record the exact SDK version that `uv` resolves, update `uv.lock`, and use the docs for that installed major version. If you intentionally choose v1 compatibility, document why.

7. **Official MCP Python SDK — `Servers > Tools` and `Structured Output`** - READ

   <https://py.sdk.modelcontextprotocol.io/servers/tools/>

   <https://py.sdk.modelcontextprotocol.io/servers/structured-output/>

   Read:
   - typed parameters and generated input schema;
   - docstrings/descriptions;
   - structured return values;
   - error handling expectations;
   - tool annotations only if their semantics are accurate.

   ProcureRAG question: which parts of `QueryRequest` and `QueryResponse` should become the MCP tool schema, and which internal fields must stay private?

8. **Official MCP Python SDK — `Testing`** - READ

   <https://py.sdk.modelcontextprotocol.io/get-started/testing/>

   Read the in-memory `Client(server)` pattern. The required deterministic tests should not need a subprocess, port, retrieval model, provider key, or live MCP host.

9. **Official MCP Python SDK — `Running your server` / transport guidance** - READ

   Follow the current v2 navigation from the SDK docs and confirm the exact stdio command for the installed version. Also note the documented Inspector command:

   ```bash
   uv run mcp dev src/mcp_server.py
   ```

   The Inspector is a Node application, so this path also requires `npx` on `PATH`. If that prerequisite is missing, record the exact error and use the SDK's in-memory client as the equivalent protocol-level evidence; do not call a plain Python function test “Inspector evidence.”

### Block C — workflow-server pattern, 25–35m

10. **Hugging Face MCP Course — Unit 3 `Advanced MCP Development: Building Custom Workflow Servers for Claude Code`** - READ

    <https://huggingface.co/learn/mcp-course/en/unit3/introduction>

    Read:
    - `Module 1: Build MCP Server`;
    - skim `Module 2: GitHub Actions Integration` for the tools/prompts separation;
    - skim `Module 3: Slack Notification` only for the multi-primitive pattern.

    ProcureRAG question: why should the MCP server expose structured domain capability and let the host provide intelligence, instead of embedding a second orchestration policy inside the server?

### Optional companion source

11. **DeepLearning.AI / Anthropic — `MCP: Build Rich-Context AI Apps with Anthropic`**

    Use only as a companion for tools/resources/prompts and local-versus-remote server concepts. The official protocol and Python SDK docs above remain the implementation source of truth.

## Day 25 objective

By the end of Day 25, Juan should be able to answer:

> “How does an MCP host discover and safely call ProcureRAG, which existing application boundary does the tool reuse, what typed input/output contract is exposed, what happens for blocked and HITL-pending requests, why is stdio the first transport, how was the protocol exercised through a real client or Inspector, and which Week 5 claims are now genuinely proven?”

The portfolio artifact is a **small MCP adapter around existing ProcureRAG behavior**. It must not duplicate retrieval, bypass the Day 20/21 guard and role boundary, silently approve a recursive pass, turn on a paid LLM by default, or expose raw traces/secrets.

## Starting state

### Repository at kickoff

```text
date: 2026-10-22
branch: main
commit: a5842de (Merge pull request #8 from juanfpinzon/docs/day24-closure)
git status: clean
Python target: >=3.11
MCP dependency: absent from pyproject.toml / uv.lock
existing workflows: ci.yml, live-eval.yml, deploy.yml
```

Secret-free kickoff gates:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
DEEPEVAL_TELEMETRY_OPT_OUT=1
OMP_NUM_THREADS=1

pytest: 387 passed in 10.05s
compileall src tests scripts: clean
Ruff src tests scripts: All checks passed!
frozen fixture regression: 7/7 as expected, exit 0
current retrieval verification: 6 x [OK], exit 0
graph regression: 6/6 contracts passed, 4 counted stand-in LLM calls, exit 0
git diff --check: clean
git status --short: clean
```

### Strongest reusable boundary

Day 21 already provides the contract the MCP adapter should preserve:

- `QueryRequest`: `query`, required caller-asserted `role`, optional evaluation-only `query_id`, optional reviewer `decision`;
- `QueryResponse`: typed `status`, display-safe `text`, source identifiers, guard findings, optional approval request, run id, and caveats;
- `run_query_events(service, body)`: the one guarded pipeline behind `/query` and `/query/stream`;
- `ProcureRAGService`: injected retrieval and LLM boundaries, labeled queries, confidentiality mapping, and a process-local limiter;
- `build_live_service()`: the real long-lived service with the two retrieval models loaded once.

The MCP tool should adapt this boundary rather than call `agent_graph.py` or the retriever directly. A direct graph/retrieval call could skip input-length validation, prompt-injection/PII checks, topic scope, role-based confidentiality filtering, HITL policy, output withholding, and the user-safe response shape.

### Day 24 handoff

Day 24 is closed and gives Day 25 a strong delivery baseline:

- three required CI jobs protect `main`;
- current retrieval and graph route contracts are non-zero gates;
- the real `linux/amd64` image is built and smoked;
- the deploy lane gates the exact image it pushes, then deploys by digest;
- Azure OIDC, one green deployment, a fail-closed sign-in, a refused push, a remote CI-refusal path, and a real rollback were exercised;
- both disposable Azure resource groups are deleted;
- live Q091 answer quality remains red because generation drops the `usage data` step despite recovered evidence.

Day 25 does not need to reopen Azure or “fix” Q091. It must keep that live-answer caveat visible in the Week 5 inventory.

## Key concepts to nail today

### 1. MCP is an interoperability boundary, not a replacement for FastAPI or the graph

The **host** is the user-facing AI application. It contains an MCP **client**, usually one client connection per server. The ProcureRAG MCP **server** advertises capabilities. The host decides when to invoke a tool; the server validates input, runs the domain operation, and returns structured data.

FastAPI and MCP solve different integration problems. FastAPI exposes an application-owned HTTP API to arbitrary HTTP clients. MCP standardizes capability discovery and invocation for AI hosts. Both can adapt the same core service. Neither should become the only place where security, retrieval, or HITL rules live.

### 2. Capability type encodes who controls the interaction

- A **tool** performs computation or retrieval when the model/host calls it. Day 25's required artifact is one tool.
- A **resource** supplies read-only context chosen by the application. A sanitized static Week 5 gate summary is a valid stretch resource; raw corpus text or raw traces are not automatically safe resources.
- A **prompt** is a reusable user-selected workflow/template. A “review this procurement answer against its cited sources” prompt is a stretch artifact, not the required core.
- **Sampling** lets a server request model work from the client/host. It is out of scope today: ProcureRAG already has an explicit live-provider boundary, and adding server-initiated model calls would blur cost, trust, and recursion limits.

### 3. Reuse one domain contract; do not build a parallel MCP-only pipeline

Recommended required tool name: **`answer_procurement_question`**.

Recommended input contract:

- `query: str` — required, same 1–500 character rule;
- `role: "requester" | "buyer"` — required and explicitly documented as caller-asserted, not authenticated;
- `query_id: str | None` — evaluation replay only and valid only with the exact labeled question;
- optional decision fields that preserve `approve` / `edit` / `reject` semantics without silent approval.

Recommended output contract: a structured equivalent of `QueryResponse`. Preserve at least:

- `status`;
- safe `text`;
- source identifiers and citation flags;
- guard findings;
- `approval_request` for `pending_approval`;
- `run_id` and caveats.

Do **not** expose raw chunk text, the unredacted trace row, environment values, provider errors containing credentials, or internal exceptions. A blocked input and a valid `pending_approval` outcome are successful domain responses, not protocol crashes.

The exact Python structure is Juan's decision. The important architectural test is whether the HTTP and MCP adapters reach the same guarded service behavior rather than implementing two policies that can drift.

### 4. Build the expensive service once per server process

The two retrieval models are long-lived process state. A tool handler that calls `build_live_service()` on every invocation would reload models, multiply latency/memory, and create a new process-local limiter each time. Use the SDK's supported server lifespan/dependency mechanism, or another explicit one-time construction seam, and inject a fake service in deterministic tests.

Keep `PROCURERAG_LIVE_LLM=0` and both LangSmith flags false for required evidence. Day 25 does not require a paid call. If Juan chooses a live smoke, it is optional, bounded, and separately labeled.

### 5. Start with stdio and treat stdout as protocol-only

Use local **stdio** first:

- no listening port;
- the host starts the server as a subprocess;
- the client/server lifecycle and tool discovery are still real MCP;
- no new remote authentication, TLS, CORS, ingress, or public exposure problem.

For a stdio server, stdout carries protocol messages. Human logs and model-loading diagnostics must not corrupt that stream; send intentional diagnostics to stderr or configure logging according to the installed SDK's guidance. Verify this with a real client/Inspector call, not only a direct function test.

Remote Streamable HTTP is a future deployment choice. Do not expose an unauthenticated MCP endpoint just because Day 23 proved a temporary public FastAPI deployment.

### 6. Test at three layers and name each claim precisely

1. **Pure domain adapter tests with fakes** — validate mapping into the existing service and safe response handling.
2. **In-memory MCP client tests** — prove discovery, generated schema, tool invocation, structured output, and error behavior through the SDK protocol path without ports/models/keys.
3. **Real local Inspector or stdio client evidence** — prove the actual server process starts, lists the tool, loads the service once, and returns real deterministic ProcureRAG behavior with live LLM/tracing off.

A direct `answer_procurement_question(...)` Python call proves the function, not MCP. An Inspector screenshot with no recorded command/output proves little. Capture exact commands, tool list/schema, representative call summaries, duration, and exit/cleanup state.

## Artifact contract Juan should design before coding

Record these decisions in the learning log before implementation:

1. **SDK line and exact resolved version** — v2 is recommended from the current official docs; record the lockfile result.
2. **Dependency placement** — whether `mcp` is a runtime dependency and the CLI extra is development-only, or another justified arrangement.
3. **Server object and transport** — stdio required first; remote transport deferred unless separately secured.
4. **Required tool** — name, description, typed arguments, structured result model, and whether annotations are accurate.
5. **Reuse seam** — which existing `api.py` domain/service functions the adapter calls and how model/service startup happens once.
6. **Safety mapping** — input limits, labeled-query consistency, role/confidentiality filtering, injection/PII/scope guards, HITL pending state, output withholding, and exception sanitization.
7. **Test seam** — how deterministic tests inject a fake service/client without loading models or using keys.
8. **Evidence boundary** — what the in-memory client proves, what Inspector/stdio proves, and what remains unproven.
9. **Optional primitive decision** — resource/prompt added only if the one tool is already clean; sampling explicitly deferred.

## Recommended 6-hour split

### Block 0 — Reactivate the baseline, 20–25m

- Read HER-293, the end of Day 24's learning-log entry, and this route.
- Re-run the kickoff commands if your working copy differs from commit `a5842de`.
- Confirm there is no MCP dependency or server module yet.
- Write one sentence for what MCP adds beyond FastAPI and one sentence for what it does not add.

### Block 1 — Exact readings, 105–135m

Complete Blocks A–C above. For each source, record one applied ProcureRAG takeaway.

Minimum reading stop condition:

- explain host/client/server without mixing them;
- explain tool/resource/prompt control boundaries;
- explain initialization → discovery → call;
- explain stdio versus Streamable HTTP;
- identify the installed SDK major/version and its matching docs.

### Block 2 — Design the artifact contract, 35–45m

Fill the nine decisions above. Then draw this boundary in your own words:

```text
MCP host
  -> MCP client
    -> stdio MCP server
      -> typed answer_procurement_question adapter
        -> existing guarded ProcureRAG service contract
          -> retrieval / graph / optional LLM
        <- safe structured QueryResponse-shaped result
    <- MCP tool result
  <- host decides how to present/use it
```

Before coding, trace Q001, Q091-without-decision, and an injection-shaped request through the proposed adapter. If any path bypasses the current API guard/HITL behavior, revise the design.

### Block 3A — Juan-owned implementation, 90–120m

Juan implements the smallest complete artifact:

1. add the chosen MCP dependency and update `uv.lock` reproducibly;
2. create the MCP server module;
3. expose exactly one required tool, `answer_procurement_question` or a clearly justified equivalent;
4. construct the real service once per process;
5. preserve live-LLM-off and no-tracing defaults for required evidence;
6. return structured, safe, bounded output;
7. add deterministic tests using fakes plus the SDK's in-memory client;
8. keep stdout protocol-safe in stdio mode.

Do not add a resource, prompt, remote transport, authentication system, or second tool until the required tool passes.

### Block 3B — fallback if SDK/Inspector setup blocks, 45–60m

A legitimate fallback is:

- dependency and lock update complete;
- server/tool contract implemented against the installed SDK;
- pure adapter tests pass;
- in-memory MCP client lists and calls the tool;
- exact Inspector/host blocker recorded, including command, stderr/error, SDK version, Python version, and whether `npx` is present;
- next retry path is explicit.

That is a **protocol-tested local scaffold**, not full Inspector/host evidence. Do not label a direct Python call or a hand-written JSON example as an MCP client test.

### Block 4 — real protocol evidence and Week 5 inventory, 45–60m

Required representative calls with live LLM off:

1. **Q001 control** — tool is discovered and called; expected non-live status, safe sources, no provider call.
2. **Q091 without decision** — `pending_approval`, approval request present, no retrieval/model run id or sources if the reused boundary preserves Day 21 behavior.
3. **Blocked input** — injection-shaped or off-topic input returns a safe blocked domain result and no internal exception/secret.
4. **Invalid schema** — missing role, over-long query, or invalid decision is rejected through the MCP/tool schema or adapter validation with sanitized error behavior.

Also verify:

- the service/models are initialized once, not once per call;
- no provider key is required;
- stdout is not polluted in stdio mode;
- no raw trace/chunk text or environment value appears;
- the process exits cleanly;
- the full local gates remain green.

Then add a Week 5 gate inventory to `docs/eval-report.md` with one row per day:

| Gate area | Primary artifacts | Strongest real evidence | Status | Honest caveat / next weakness |
|---|---|---|---|---|
| Day 21 — FastAPI async/streaming surface | `src/api.py`, API tests | real local/container HTTP and SSE evidence | fill | caller-asserted role, stateless approval, process-local rate limit |
| Day 22 — Docker | Dockerfile, `.dockerignore`, runbook | real arm64 + amd64 build/run/smoke evidence | fill | model/base revisions and image size |
| Day 23 — Azure | template/runbook/evidence | real Container Apps deployment, probes, logs, cleanup | fill | no persistent deployment/authentication |
| Day 24 — eval-gated CI/CD | workflows, regressions, smoke script | remote green/red/refusal/deploy/rollback evidence | fill | Q091 live answer-quality red; rebuild rather than CI artifact promotion |
| Day 25 — MCP | server/tool/tests/evidence | in-memory client plus Inspector/stdio call | fill | local stdio only; caller-asserted role; no remote MCP auth |

Do not flatten “documented fallback,” “scaffolded,” and “exercised” into one `Done` status. Use the strongest honest status for each row.

### Block 5 — Learning log and interview drill, 30–40m

- Replace every Day 25 TODO with real evidence or an explicit blocker.
- Record exact commands and versions.
- Record one failure or confusing point and how it was resolved.
- Answer the interview drill without notes.
- Send the review prompt below. Do not move HER-293 or HER-270 to Done before review.

## Target evidence by end of day

### Sources and design

- [ ] Every required source/section is read with one ProcureRAG-specific takeaway.
- [ ] Host, client, server, tools, resources, prompts, and sampling are distinguished correctly.
- [ ] Installed SDK major/version and matching docs are recorded.
- [ ] Tool contract and reuse seam are written before implementation.
- [ ] stdio is the required first transport; remote exposure is explicitly deferred or separately secured.

### Dependency and implementation

- [ ] MCP dependency placement is intentional and `uv.lock` is updated.
- [ ] One useful MCP server/tool exists under Juan-owned implementation.
- [ ] The tool uses typed inputs and a structured safe result.
- [ ] The tool reuses the existing guarded service behavior rather than direct raw retrieval/graph access.
- [ ] Expensive model/service state is initialized once per process.
- [ ] Live LLM and tracing remain off by default for required evidence.
- [ ] No silent HITL approval, raw trace, raw secret, or unsafe exception detail is exposed.

### Protocol and test evidence

- [ ] Deterministic pure-adapter tests exist.
- [ ] An in-memory MCP client discovers and calls the tool.
- [ ] Schema discovery proves required/optional arguments and structured output.
- [ ] Q001, Q091 pending approval, blocked input, and invalid input paths are covered.
- [ ] Inspector or an equivalent real stdio client lists/calls the tool, or the exact blocker is recorded and status remains scaffold/protocol-tested rather than full.
- [ ] stdio output is protocol-safe and process cleanup is verified.

### Week 5 gate evidence

- [ ] `docs/eval-report.md` inventories API, Docker, Azure/fallback, CI/CD, and MCP with artifact/evidence/status/caveat columns.
- [ ] Day 24's Q091 live generation-quality failure remains visible.
- [ ] Deleted Azure resources are not described as a currently live deployment.
- [ ] MCP is described as complementary to FastAPI, not a replacement.
- [ ] Any local-only, unauthenticated, or caller-asserted identity boundary is explicit.

### Final gates

- [ ] `uv sync --locked --dev` succeeds.
- [ ] `pytest -q` passes with the new MCP tests.
- [ ] `compileall -q src tests scripts` is clean.
- [ ] Ruff passes.
- [ ] frozen and current retrieval regressions pass.
- [ ] graph regression passes.
- [ ] `git diff --check` passes.
- [ ] `git status --short` contains only intentional Day 25 artifacts.
- [ ] A real remote CI run is recorded after the changes reach a branch/PR; local green is not called remote CI.

## Baseline and review commands

Use the repo's existing explicit no-live/no-trace contract:

```bash
export PROCURERAG_LIVE_LLM=0
export LANGSMITH_TRACING=false
export LANGSMITH_TRACING_V2=false
export DEEPEVAL_TELEMETRY_OPT_OUT=1
export OMP_NUM_THREADS=1

uv sync --locked --dev
uv run pytest -q
uv run python -m compileall -q src tests scripts
uv run python -m ruff check src tests scripts
uv run python src/regression_suite.py
HF_HUB_OFFLINE=1 uv run python src/regression_suite.py --verify-retrieval
HF_HUB_OFFLINE=1 uv run python src/graph_regression.py
git diff --check
git status --short
```

Add the exact installed-SDK commands Juan selects. Expected evidence shape:

```bash
# SDK/package version
uv run python -c "import importlib.metadata; print(importlib.metadata.version('mcp'))"

# in-memory protocol tests live inside pytest
uv run pytest -q tests/test_mcp_server.py

# Inspector / real stdio client, exact command confirmed against installed major
uv run mcp dev src/mcp_server.py
```

Do not paste a provider key into a command, route doc, learning log, screenshot, Linear comment, or chat.

## Interview drill

1. **What are the MCP host, client, and server in this ProcureRAG demo?**
   - Expected answer shape: the host is the user-facing AI application; its client maintains the MCP connection; ProcureRAG is the server exposing typed capabilities. The LLM/host decides whether to invoke the tool; the server executes the bounded domain contract.

2. **Why is `answer_procurement_question` a tool rather than a resource or prompt?**
   - Expected answer shape: it performs computation/retrieval based on arguments. A resource is read-only context selected by the application, while a prompt is a reusable workflow/template selected by a user. The control boundary matters.

3. **Why reuse the Day 21 service contract rather than call the retriever directly?**
   - Expected answer shape: direct retrieval skips validation, injection/PII/topic checks, role filtering, HITL, output/citation handling, and the stable response contract. MCP and FastAPI should be adapters over one domain boundary.

4. **Why start with stdio instead of remote Streamable HTTP?**
   - Expected answer shape: stdio is local, host-managed, and needs no listening network surface. Remote HTTP adds authentication, TLS, session/origin/ingress, deployment, and abuse-control decisions. Transport choice does not remove authorization needs.

5. **What does tool discovery prove?**
   - Expected answer shape: after initialization/capability negotiation, the client can list the tool's name, description, and schema. It does not prove the tool's implementation is correct, safe, or fast; representative calls and tests must prove behavior.

6. **What is the difference between a direct Python test, an in-memory MCP client test, and Inspector/stdio evidence?**
   - Expected answer shape: direct tests prove adapter logic; the in-memory client proves SDK protocol discovery/call/schema paths; Inspector or a subprocess client proves the real server startup/transport/process boundary. Each has a different claim.

7. **How does the tool preserve human-in-the-loop behavior?**
   - Expected answer shape: Q091 without a decision returns `pending_approval` and an explicit request; it never silently approves. A subsequent call carries approve/edit/reject, still subject to validation and guards. The current identity/approval record remains caller-asserted and stateless.

8. **How do tools, resources, prompts, and sampling differ in control and risk?**
   - Expected answer shape: tools are model-invoked actions/computation; resources are application-controlled context; prompts are user-controlled templates; sampling is server-initiated model work. Sampling and write tools raise cost/agency concerns and are intentionally out of scope.

9. **Why must a stdio server keep stdout clean?**
   - Expected answer shape: stdout is the protocol channel. Human logs/model progress on stdout can corrupt JSON-RPC framing. Use SDK-supported logging/stderr and verify through a real client.

10. **Why doesn't MCP replace the FastAPI API?**
    - Expected answer shape: MCP standardizes AI-host discovery and invocation; FastAPI is a general HTTP service contract. They serve different clients and transports but should share the same application service. The API also remains the deployed/container-smoked surface from Week 5.

11. **What does the Week 5 gate now prove, and what remains weak?**
    - Expected answer shape: exercised API, container, Azure deployment/cleanup, eval-gated CI/CD/deploy, and a local MCP tool. Remaining weaknesses include Q091 answer quality, caller-asserted identity/HITL, no durable review/trace store, local-only MCP without remote auth, model/base revision mutability, and no persistent live Azure service.

12. **How would you productionize the MCP server without overexposing ProcureRAG?**
    - Expected answer shape: choose remote transport only with authenticated identity mapped to roles, authorization before retrieval, TLS/ingress controls, durable audit/HITL, bounded rate/cost, sanitized outputs/logs, pinned artifacts, monitored deployment, and protocol/client compatibility tests.

## Hermes review protocol

When Juan sends the review prompt, Hermes will:

1. read the installed dependency/lock change, MCP module, tests, Week 5 gate inventory, and completed learning-log entry;
2. trace every tool input to the existing validation/guard/role/HITL boundary and every output field back to the safe response contract;
3. verify the service/models initialize once rather than per call;
4. run the full baseline commands plus MCP-specific tests/client commands;
5. inspect discovery/schema and call results for Q001, Q091 pending approval, blocked input, and invalid input;
6. verify stdout/log/secret hygiene and live-LLM-off behavior;
7. distinguish pure function, in-memory protocol, Inspector/stdio, remote CI, and remote deployment evidence;
8. review the Week 5 inventory for stale or inflated claims;
9. quiz Juan on the twelve questions above;
10. point out issues for Juan to fix without rewriting his implementation.

## Review prompt to send Hermes

> “Day 25 MCP + Week 5 gate work is ready for review. Please inspect the MCP SDK/version and lock change, tool schema and structured output, reuse of the Day 21 guarded service boundary, one-time service/model initialization, stdio/log safety, in-memory client and Inspector/stdio evidence for Q001/Q091/blocked/invalid cases, full test/regression gates, Week 5 inventory, and my interview answers. Juan owns all implementation.”

## Stop condition

Day 25 is ready for review only when:

1. one useful typed MCP tool exists and reuses the guarded ProcureRAG service boundary;
2. deterministic adapter and in-memory MCP client tests pass;
3. a real Inspector/stdio client has listed and called the tool, or the exact external prerequisite blocker is documented and the status is honestly labeled incomplete;
4. Q001, Q091 pending approval, blocked input, and invalid input evidence is recorded with live LLM/tracing off;
5. the full local gates pass and a remote CI run is identified when available;
6. the Week 5 gate inventory separates exercised, scaffolded, deleted, and still-open evidence;
7. the learning log has no completion TODOs left;
8. Juan can answer the interview drill without notes.

Do not close HER-293 or the parent HER-270 on route creation or passing tests alone. First send the review prompt. After Day 25 passes, close HER-293; then run the separate HER-270 parent-gate review across all five children and the cumulative evidence.