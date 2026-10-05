# Day 19 — Observability Traces and Structured Outputs

Date: 2026-10-05 kickoff.

Linear: HER-286 — Day 19 loop: observability traces + structured outputs.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

No new Boot.dev chapter today. Day 16 completed Boot.dev Chapter 11 (`Agentic` → `Recursive RAG`, `Agentic Search`), Day 17 made the retrieval loop graph-shaped, and Day 18 added checkpointing/HITL/time-travel controls. Day 19 makes that agentic path **inspectable and schema-disciplined**: trace the route decisions, preserve reviewable run evidence, and stop treating the final answer/diagnostic as an ad hoc string.

Primary source:

- **Hugging Face Agents Course — Bonus Unit 2: Agent Observability and Evaluation**
  - `Introduction`: <https://huggingface.co/learn/agents-course/en/bonus-unit2/introduction>
  - `What is agent observability and evaluation?`: <https://huggingface.co/learn/agents-course/en/bonus-unit2/what-is-agent-observability-and-evaluation>
  - `Monitoring and evaluating agents` / `Bonus Unit 2: Observability and Evaluation of Agents`: <https://huggingface.co/learn/agents-course/en/bonus-unit2/monitoring-and-evaluating-agents-notebook>
  - `Quiz: Evaluating AI Agents`: <https://huggingface.co/learn/agents-course/bonus-unit2/quiz>

LangGraph / LangSmith companion sources:

- **LangChain Academy — Foundation: Introduction to LangGraph - Python**: <https://academy.langchain.com/courses/intro-to-langgraph>
  - Module 1 `Introduction` → `Lesson 3: LangSmith Studio`.
  - Module 6 `Deployment` preview/reference → `Deployment Concepts`, `Creating a Deployment`, `Connecting to a Deployment`, `Double Texting`, `Assistants`.
- **LangGraph deployment docs**: <https://docs.langchain.com/oss/python/langgraph/deploy>
  - LangSmith Cloud hosts stateful, long-running LangGraph agents; Studio can test deployed graphs; deployments expose an API URL for SDK/REST access.
- **LangSmith double-texting docs**: <https://docs.langchain.com/langsmith/double-texting>
  - Deployment-level strategies: `Enqueue`, `Reject`, `Interrupt`, `Rollback`; not available in the OSS framework alone.
- **LangSmith tracing for LangGraph**: <https://docs.langchain.com/langsmith/trace-with-langgraph>
  - Reactivate from Day 18: tracing should show node/span/run-tree evidence, not just local print output.

Structured-output companion sources:

- **LangChain structured output docs**: <https://docs.langchain.com/oss/python/langchain/structured-output>
  - `create_agent(..., response_format=...)`; structured result returned under `result["structured_response"]`.
  - Strategy choices: `ProviderStrategy`, `ToolStrategy`, direct schema type, or `None`.
  - Passing a Pydantic model lets LangChain select provider-native structured output when available, otherwise tool-based structured output.
- **LangChain `create_agent` reference**: <https://reference.langchain.com/python/langchain/agents/factory/create_agent>
  - Confirms `response_format` accepts a Pydantic model / schema strategy and that the agent is a model-tool loop.
- **OpenAI Structured Outputs guide**: <https://platform.openai.com/docs/guides/structured-outputs>
  - Structured Outputs enforce a JSON Schema; SDKs can derive schemas from `pydantic.BaseModel`; use structured text response for final structured model output, function calling for tool/action interfaces.
- **Pydantic models docs**: <https://docs.pydantic.dev/latest/concepts/models/>
  - `BaseModel`, validation, `model_validate`, `model_validate_json`, `model_dump`, `model_json_schema`, and `ValidationError`.

Exact source-note: LangChain Academy lesson pages may require enrollment/login. Use the public course/module menu for exact lesson names, then ground API claims in the installed project versions where possible (`langchain 1.4.0`, `langgraph 1.2.11`, `langsmith 0.12.5`).

## Day 19 objective

Build a reviewable observability and structured-output layer around the Day 17/18 agentic RAG path. By the end of the day, Juan should be able to show one trace/evidence artifact and one structured result contract that answer:

> “For Q091/Q092 and the 15 `report_gap` cases, what exactly happened inside the graph, why did it stop, what evidence changed, what did the answer/refusal claim, and can downstream code validate that object without scraping prose?”

This is not a generic tracing demo. The artifact must be anchored in ProcureRAG’s actual measured weak points: Q091’s Band 3 chunk gap, Q092’s missing `CONTRACT-005`/`POL-002` docs, Day 18’s `report_gap` policy, and the remaining difference between local CI-safe evidence and live/SaaS observability.

## Starting state

Current repo evidence at kickoff:

- `src/agent_graph.py` — Day 17 LangGraph `StateGraph` with route distribution still at 76 direct `generate`, 2 `recursive_retrieve → generate` (Q091/Q092), and 15 `report_gap`.
- `src/agent_control_plane.py` — Day 18 controlled graph with `InMemorySaver`, `interrupt()` approval before `recursive_retrieve`, approve/edit/reject decisions, state history/time-travel replay, and local trace/checkpoint printing.
- `tests/test_agent_control_plane.py` — 12 deterministic tests for checkpoint isolation, pausing/resuming, approval/edit/reject, invalid-decision re-ask, and time-travel behavior.
- `docs/eval-report.md` / `docs/learning-log.md` — Day 18 evidence says LangSmith tracing was **not captured yet**; local trace/checkpoint output is the current evidence.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query labeled source. Do not create `data/golden_queries.jsonl`.
- `generation.main()` and `regression_suite.py` remain single-pass and not graph-aware; the frozen Q091 fixture still reports `term-level gap OPEN: missing ['Band 3']` in the old single-pass lane.

Baseline checks at kickoff:

```bash
./.venv/bin/pytest -q
# 244 passed in 3.23s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# All cases match their currently expected state (frozen fixtures).
# The current retrieval pipeline still matches every case's expectation.
# Q091 frozen fixture lane still shows: term-level gap OPEN: missing ['Band 3'].

LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_graph.py --all-queries-summary
# Route distribution over 93 queries: generate 76 | report_gap 15 | recursive_retrieve -> generate 2 (Q091, Q092)
# First-pass evidence gap: 17. Fixed by recursive pass: 2. Ended in report_gap: 15.

LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_control_plane.py --query-ids Q091
# Q091 pauses for approval before recursive_retrieve, resumes with approve,
# reaches ['recursive_retrieve', 'generate'] / fixed_after_second_pass,
# saves 8 checkpoints, and time-travel reject replays with 0 pass-1 retrieval calls.
```

Git status at kickoff was clean on `main` before this Day 19 route/log scaffold was added.

## Key concepts to nail today

### Traces are the execution story; evals are the quality judgment

An eval table says whether the system met a criterion. A trace explains how it got there: nodes, tool calls, retrieval configs, latency/cost if available, model calls, interrupts, approvals, errors, and outputs. Day 19 should keep those separate.

For ProcureRAG, `pytest`, `regression_suite.py`, and `--all-queries-summary` are offline/CI-safe checks. LangSmith/Langfuse traces or local JSONL trace rows are observability artifacts. A trace row by itself does not prove answer quality; it gives the evidence needed to debug the quality result.

### The trace contract must be stable enough to compare runs

Day 18’s local `trace` list is helpful for a human, but Day 19 needs a structured contract. A useful row/run object should include at least:

- run metadata: `run_id`, `thread_id`, timestamp, code version if easy, query id/type;
- route: `route_history`, `stop_reason`, approval decision if any;
- retrieval steps: pass number, retrieval config, original/follow-up query, doc/chunk ids returned, added chunks;
- evidence verdicts: missing docs/chunks before and after, trigger reason, `report_gap` reason;
- answer/refusal: structured status, citations, uncertainty/refusal reason;
- observability info: local artifact path and/or SaaS trace URL/id; optional latency/cost if measured.

It is fine if Day 19 starts with local JSONL and one LangSmith trace handle. What matters is that the fields let Juan compare Q091/Q092 and diagnose at least one `report_gap` example without rereading free-form logs.

### Structured output is an application contract, not “pretty JSON”

Pydantic/structured output matters because downstream code needs to know whether the graph produced an answer, a refusal, a diagnostic gap report, or an error. A final string like `[not generated: evidence was complete...]` is useful for a demo, but brittle for an app, a regression suite, or a UI.

Day 19’s schema should explicitly model states such as:

- answer vs. refusal/gap report vs. not generated;
- evidence status (`complete`, `missing_docs`, `missing_chunks`, `human_rejected`, etc.);
- citations/source ids and whether citation validation passed;
- caveats/uncertainty and missing evidence names;
- trace handle/path so an answer can be audited.

The schema can wrap deterministic graph output today. It does **not** need a live LLM to be valuable.

### LangSmith/Langfuse is useful, but local evidence must stay CI-safe

HER-286 allows LangSmith or Langfuse. Given this repo already uses LangGraph/LangChain and has LangSmith variables from Day 18, the recommended route is:

1. try **LangSmith** first for one Q091 or Q092 controlled-graph run;
2. record the trace URL/id or, if a URL cannot be shared, the trace/run id plus project and exact command;
3. still produce a local JSONL/table fallback so review does not depend on a SaaS UI.

If SaaS setup blocks progress, do not fake a trace URL or screenshot. Write a local structured trace artifact and document that SaaS observability is deferred.

## Target evidence by end of day

- [ ] Course/source work recorded with exact lesson/page names:
  - [ ] HF Agents Course Bonus Unit 2 `Introduction`.
  - [ ] HF Bonus Unit 2 `What is agent observability and evaluation?`.
  - [ ] HF Bonus Unit 2 `Monitoring and evaluating agents` notebook.
  - [ ] HF Bonus Unit 2 `Quiz: Evaluating AI Agents`.
  - [ ] LangChain Academy Module 1 `Lesson 3: LangSmith Studio`.
  - [ ] LangChain Academy Module 6 deployment preview/reference: `Deployment Concepts`, `Creating a Deployment`, `Connecting to a Deployment`, `Double Texting`, `Assistants`.
  - [ ] LangChain structured-output docs and `create_agent.response_format` reference.
  - [ ] OpenAI Structured Outputs guide and Pydantic `BaseModel` model docs.
- [ ] A trace/evidence contract is written or implemented, covering route, retrieval passes, approval/HITL decision, doc/chunk ids, missing-evidence signals, result status, and trace handle/path.
- [ ] At least one ProcureRAG run produces inspectable trace evidence:
  - Preferred: LangSmith trace for `src/agent_control_plane.py --query-ids Q091` or Q092, plus local artifact.
  - Acceptable fallback: local JSONL trace/report with exact reproduction command and sample row.
- [ ] The trace evidence includes Q091 or Q092 and at least one `report_gap` example from the 15-query set, unless Juan records why the second case was deferred.
- [ ] A Pydantic/structured-output schema exists for the final result object or diagnostic report.
- [ ] Tests reject or normalize invalid structured output and assert that one trace row includes the key debug fields.
- [ ] Docs separate CI-safe evidence from live/SaaS evidence. No hidden dependence on provider credentials for the standard test suite.
- [ ] `docs/eval-report.md` and/or `docs/learning-log.md` contains the real command output, trace path/handle, and structured-output decision.
- [ ] Juan can explain offline eval vs. online observability vs. unit tests, and why structured outputs reduce production risk.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and choose the evidence lane, 30–45m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_graph.py --all-queries-summary
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_control_plane.py --query-ids Q091
```

Then decide:

1. Is the primary live trace backend LangSmith, Langfuse, or local JSONL only for today?
2. Which one hard case anchors the trace proof: Q091, Q092, or both?
3. Which one `report_gap` case will be included for contrast: e.g. Q014, Q023, or Q090?
4. Is the structured object an **answer result**, a **diagnostic trace row**, or both?

Recommendation: use LangSmith if one trace can be captured quickly, but make the CI-safe artifact local JSONL/Pydantic so review does not depend on the web UI.

### Block 1 — Course/source work, 90–120m

Read and map notes to ProcureRAG:

1. HF Bonus Unit 2:
   - `Introduction` — why observability matters for deployed agents.
   - `What is agent observability and evaluation?` — logs/metrics/traces, offline vs. online eval, real-time feedback, drift.
   - `Monitoring and evaluating agents` notebook — trace/span vocabulary, instrumentation, metrics, feedback, LLM-as-judge, dataset/offline evaluation.
   - `Quiz: Evaluating AI Agents` — use it as a self-check.
2. LangGraph/LangSmith:
   - Module 1 `LangSmith Studio` — what Studio/trace inspection adds beyond local print output.
   - Module 6 deployment preview — what deployment, Studio, double-texting, and Assistants imply for future ProcureRAG; do not implement deployment today unless it is trivial.
   - LangGraph deployment and double-texting docs — especially the distinction between OSS graph features and LangSmith Deployment/Agent Server features.
3. Structured outputs:
   - LangChain structured output: `response_format`, `ProviderStrategy`, `ToolStrategy`, `structured_response`.
   - OpenAI Structured Outputs: schema adherence, refusal detection, function-calling vs final-response structuring.
   - Pydantic models: `BaseModel`, validation, serialization, JSON Schema, `extra="forbid"` if Juan wants strict trace/result contracts.

Write scratch notes answering:

- Which fields in Day 18’s approval request belong in a trace row?
- Which fields in `answer`, `citations`, `stop_reason`, and `diagnoses` belong in a structured result?
- What is CI-safe evidence versus live/SaaS evidence?
- Which behavior should be validated by Pydantic and which by tests/evals?

### Block 2 — Design the artifact contract, 45–60m

Before coding, draft a small table like this in notes or docs:

| Contract piece | Required fields | Source in current code | Why it matters |
|---|---|---|---|
| Run metadata | `run_id`, `thread_id`, `query_id`, `query_type`, timestamp | `thread_config`, corpus row | Compare runs and find trace |
| Route | `route_history`, `stop_reason`, approval decision | graph state / `approval` | Explain control flow |
| Retrieval pass | pass number, query text, config, source doc/chunk ids, added chunks | `sources`, `trace`, `diagnoses` | Debug Q091/Q092 |
| Evidence verdict | missing docs/chunks before/after, trigger reason | `diagnoses` | Separate retrieval from generation |
| Result object | status, answer/refusal, citations, caveats, trace handle | graph final state | Replace ad hoc strings |
| Live handle | LangSmith URL/id or local artifact path | trace backend or file | Review/audit trail |

Keep the contract small and explainable. Do not turn this into a full observability platform.

### Block 3A — Primary route: Juan-owned trace + structured-output artifact, 120–150m

Possible artifact shape, for Juan to design and implement:

- A docs decision note in `docs/eval-report.md` doc explaining:
  - observability backend chosen(LangSmith , API key and other needed stuff in .env);
  - local trace schema;
  - structured result schema;
  - CI-safe vs. live/SaaS evidence boundary.
- A small module or extension, if needed, that can:
  - run selected query ids through the controlled graph;
  - emit one structured trace record per run or per step;
  - validate/serialize records with Pydantic;
  - attach a LangSmith trace id/url if available.
- Tests that do **not** require LangSmith/Langfuse credentials or live LLMs:
  - valid trace row round-trips through Pydantic;
  - missing required fields fail validation;
  - invalid `status`/`stop_reason`/citation shape is rejected or normalized;
  - one Q091-style fake run contains the expected debug fields.
- A demo command that prints or writes a trace example for Q091/Q092 and one `report_gap` case.

Recommended behavior:

1. Preserve Day 18 graph behavior and route distribution. This day observes and structures; it should not silently change retrieval policy.
2. Include both before/after evidence for Q091/Q092 if tracing a recursive case.
3. Include at least one `report_gap` row, because those 15 cases drive the next policy decision.
4. If a live trace is captured, record the exact command and trace handle. If it is not captured, say so and keep the local artifact honest.
5. Avoid provider-token dependence in standard tests.

### Block 3B — Fallback route: local structured trace only, 60–90m

Use this if LangSmith/Langfuse setup, auth, browser access, or screenshot sharing blocks progress.

Still produce:

1. A local JSONL or printed structured table for Q091 or Q092 and one `report_gap` case.
2. A Pydantic model/schema for the trace/result object.
3. Tests for schema validation and required trace fields.
4. Docs saying LangSmith/Langfuse trace capture is deferred, with the blocker and the exact next command to try.

This fallback is acceptable because it preserves the core learning: observability as a stable event contract plus structured output validation. It is not acceptable to only summarize the HF/LangChain docs without mapping them to the ProcureRAG graph.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/learning-log.md` — Day 19 entry with exact source completion, backend choice, trace schema, sample handle/path, structured-output schema, validation behavior, gates, and remaining weakness.
- `docs/eval-report.md` or a dedicated observability doc — only if the artifact creates reusable trace/result evidence worth preserving outside the learning log.

Then answer the interview drill below without notes.

## Interview drill

1. What is the difference between logs, traces, metrics, tests, and evals?

   **Expected answer shape:** Logs are textual events. Traces are structured execution trees/spans showing what happened during one run. Metrics aggregate measurements like latency/cost/success rate. Tests assert deterministic code contracts. Evals judge task quality against examples/criteria. ProcureRAG needs all of them: tests for CI, evals for retrieval/answer quality, traces for debugging Q091/Q092 route behavior, and metrics later for production monitoring.

2. Why did Day 18’s local `trace` list not fully solve observability?

   **Expected answer shape:** It is human-readable and testable, but it is not a stable external artifact or run tree. It lacks a durable trace id/url, span hierarchy, latency/cost/model-call metadata, and easy filtering/comparison across runs. Day 19 should either send LangGraph spans to LangSmith/Langfuse or emit a local structured trace file with stable fields.

3. What fields must be present to debug Q091’s recursive retrieval path?

   **Expected answer shape:** Query id/type, route history, first-pass source doc/chunk ids, first-pass missing chunks (`POL-001::chunk-5`/`chunk-6`), proposed/approved follow-up query, retrieval config, added chunks (`POL-001::chunk-6` at minimum), final missing evidence, stop reason, answer/refusal status, citations, and trace handle/path.

4. Why is structured output better than parsing final answer prose?

   **Expected answer shape:** A schema makes status/citations/missing evidence/refusal/caveats machine-checkable. Tests can validate it; a UI can render it; evals can consume it; errors become validation failures instead of hidden string-shape drift. Prose is still useful for humans, but it should sit inside a typed result object.

5. When would you use OpenAI/Provider-native Structured Outputs vs LangChain `ToolStrategy`/`ProviderStrategy` vs plain Pydantic validation?

   **Expected answer shape:** Provider-native structured output is best for final model responses when the provider enforces the schema. LangChain `response_format` abstracts provider-vs-tool strategies for `create_agent` loops. Plain Pydantic validation is still useful for deterministic graph outputs, local trace rows, and tests even when no LLM is called. ProcureRAG can start with Pydantic around deterministic graph state and later add provider-native structured answers.

6. What does offline vs online evaluation mean in this repo?

   **Expected answer shape:** Offline eval is the labeled 93-query corpus, regression suite, retrieval metrics, and deterministic tests run before deployment. Online eval/observability would be live user/run monitoring, user feedback, cost/latency, trace review, and possibly LLM-as-judge on production traffic. Day 19 remains mostly offline/local, with one live/SaaS trace if available.

7. Why should the 15 `report_gap` cases be traced before changing policy?

   **Expected answer shape:** Because the policy choice depends on why they fail. Some may need better follow-up queries; some may be acceptable refusals; some might be caveated-answer candidates. A trace row that names missing docs, query type, route, and stop reason lets Juan choose based on evidence instead of adding a generic caveated answer path.

## Hermes review protocol

When Juan has a serious Day 19 pass ready, ask Hermes:

> Day 19 observability and structured-output work done. Review HER-286: exact HF Bonus Unit 2 / LangGraph / structured-output source notes, trace/evidence contract, local or LangSmith/Langfuse trace handle/path, Pydantic/structured-result schema, schema validation tests, CI-safe vs live evidence boundary, docs, verification outputs, and learning-log evidence. Verify pytest/compile/ruff/regression gates and do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify trace/result evidence, and either close HER-286 or return precise remaining tasks. Hermes must not replace Juan’s implementation.

## Stop condition

Day 19 is complete when:

1. The named HF Bonus Unit 2 pages, LangGraph/LangSmith sources, and structured-output sources have been completed or explicitly reviewed and summarized.
2. A trace/evidence contract exists with stable fields for route, retrieval passes, approval/HITL, missing evidence, answer/refusal/result status, and trace handle/path.
3. At least one ProcureRAG run produces inspectable trace evidence: ideally LangSmith/Langfuse plus local artifact, or a documented local-only fallback with a real reproduction command.
4. The trace evidence includes Q091 or Q092, and preferably one `report_gap` case.
5. A Pydantic/structured-output result or diagnostic schema exists.
6. Tests validate the schema and trace row shape without live credentials.
7. `docs/learning-log.md` is updated with real evidence, not imagined output.
8. Tests/compile/lint/regression gates pass, or blockers are recorded honestly.
9. Juan can explain observability vs evals and structured outputs using ProcureRAG-specific examples.

Do not close HER-286 on route creation alone. The route is the kickoff; Juan’s course work, artifact, evidence, and interview explanation are the acceptance criteria.
