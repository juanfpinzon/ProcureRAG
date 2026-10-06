# Day 20 — Guardrails and Week 4 Gate Review

Date: 2026-10-06 kickoff.

Linear: HER-287 — Day 20 loop: guardrails + Week 4 gate review.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

No new Boot.dev chapter today. Day 16 completed Boot.dev Chapter 11 (`Agentic` → `Recursive RAG`, `Agentic Search`), Day 17 made the loop graph-shaped, Day 18 added checkpointing/HITL controls, and Day 19 added trace rows plus structured outputs. Day 20 closes the Week 4 safety layer: guardrails around the agentic ProcureRAG path, plus the Week 4 gate inventory.

Primary source:

- **DeepLearning.AI short course — Safe and reliable AI via guardrails**: <https://www.deeplearning.ai/courses/safe-and-reliable-ai-via-guardrails>
  - `Introduction`.
  - `Failure modes in RAG applications`.
  - `What are guardrails`.
  - `Building your first guardrail`.
  - `Checking for hallucinations with Natural Language Inference`.
  - `Using hallucination guardrail in a chatbot`.
  - `Keeping a chatbot on topic`.
  - `Ensuring no personal identifiable information (PII) is leaked`.
  - `Preventing competitor mentions`.
  - `Conclusion`.
  - `Quiz` / self-check if available.

  Short Course Completed on 06-10-26 (including Quiz and Certification)

Security companion:

- **OWASP Top 10 for LLMs and GenAI Apps — 2025**: <https://genai.owasp.org/llm-top-10/?cat=44>
  - `LLM01:2025 Prompt Injection`.
  - `LLM02:2025 Sensitive Information Disclosure`.
  - `LLM05:2025 Improper Output Handling`.
  - `LLM06:2025 Excessive Agency`.
  - `LLM07:2025 System Prompt Leakage`.
  - `LLM08:2025 Vector and Embedding Weaknesses`.
  - `LLM09:2025 Misinformation`.
  - `LLM10:2025 Unbounded Consumption`.

  Companion docs read 06-10-26

Project companion sources:

- `docs/day-16-recursive-rag-agentic-search.md` — recursive retrieval and hard-case evidence.
- `docs/day-17-langgraph-state-graph.md` — graph/state/routing artifact.
- `docs/day-18-agent-memory-hitl-control-plane.md` — checkpointing, HITL, replay controls.
- `docs/day-19-observability-traces-structured-outputs.md` — traces, LangSmith handles, structured output, schema caveats.
- `docs/eval-report.md` and `docs/learning-log.md` — current evidence, known caveats, and remaining weaknesses.

## Day 20 objective

Build a minimal, explainable guardrail layer around the current agentic ProcureRAG flow and then run the Week 4 gate inventory. By the end of the day, Juan should be able to answer:

> “What can this RAG agent do, what is it not allowed to do, what unsafe inputs or outputs are blocked/redacted, how do HITL and structured outputs reduce blast radius, and what evidence proves Week 4 is ready to close?”

This is not a generic GuardrailsAI demo. The artifact should be anchored in ProcureRAG’s actual current risks:

- retrieved/untrusted context may contain prompt-injection-style instructions;
- user prompts or outputs may contain PII or sensitive supplier/procurement data;
- the agentic graph can take a second retrieval action and therefore needs bounded agency / approval controls;
- structured output currently guarantees shape, not answer truth;
- the 15 `report_gap` cases are still traced but not policy-resolved;
- Week 4 needs a documented, honest inventory before moving into Week 5 serving/deployment.

## Starting state

Current repo evidence at kickoff:

- `src/agentic_retrieval.py` — Day 16 bounded recursive retrieval policy, with measured Q091/Q092 recovery and known remaining `report_gap` cases.
- `src/agent_graph.py` — Day 17 LangGraph `StateGraph` with route distribution: 76 direct `generate`, 2 `recursive_retrieve → generate` (`Q091`, `Q092`), and 15 `report_gap`.
- `src/agent_control_plane.py` — Day 18 controlled graph with `InMemorySaver`, `interrupt()` approval before recursive retrieval, approve/edit/reject decisions, and time-travel replay.
- `src/agent_observability.py` — Day 19 local JSONL trace rows, LangSmith root-run handles, `AgentRunTrace`, `AgentResult`, and strict structured generation via `GeneratedAnswer`.
- `tests/test_agent_observability.py` and related tests — deterministic tests for trace/result schema, version vocabulary, empty-context behavior, citation contracts, and LangSmith in-memory run-link behavior.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query labeled source. Do not create `data/golden_queries.jsonl`.
- Current Day 19 weaknesses to carry forward:
  - structured output fixes shape, not truth;
  - citation checks prove source existence, not correct scope/application;
  - `answered` rows can ignore recovered chunks;
  - `generation.main()` and `regression_suite.py` are still single-pass and not graph-aware;
  - only one `report_gap` case (`Q014`) was traced in detail;
  - no local latency/cost fields yet;
  - no prompt-injection / PII / excessive-agency guardrail tests yet.

Baseline checks at kickoff:

```bash
./.venv/bin/pytest -q
# 275 passed in 4.14s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# All cases match their currently expected state (frozen fixtures).
# The current retrieval pipeline still matches every case's expectation.

LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_graph.py --all-queries-summary
# Route distribution over 93 queries:
# generate 76 | report_gap 15 | recursive_retrieve -> generate 2 (Q091, Q092)
# Queries with a first-pass evidence gap: 17. Fixed by the recursive pass: 2. Ended in report_gap: 15.

LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_observability.py --query-ids Q091 Q014 --output /tmp/day20-kickoff-trace.jsonl
# Q091: recursive_retrieve -> generate; fixed_after_second_pass; result status not_generated / complete.
# Q014: report_gap; trigger_detected_no_followup_query_defined; result status gap_report / missing_docs ['CONTRACT-004'].
# Wrote 2 trace row(s) to /tmp/day20-kickoff-trace.jsonl; re-read and re-validated 2.
```

Git status at kickoff was clean on `main` before this Day 20 route/log scaffold was added.

## Key concepts to nail today

### Guardrails are explicit constraints around a probabilistic system

Tests and evals tell Juan whether known cases work. Guardrails sit in the application path and enforce constraints before or after a model/agent step. In ProcureRAG, a useful guardrail is not “the model should be careful”; it is code or a schema that blocks, redacts, flags, or routes a risky behavior.

Day 20 should distinguish:

- **input guardrails:** checks on user prompts before retrieval/model calls;
- **retrieval/context guardrails:** checks on untrusted retrieved content before it influences generation;
- **action guardrails:** limits on agent/tool/retrieval actions and required human approval;
- **output guardrails:** checks on final answer text, citations, schema, PII, caveats, and unsupported claims.

### Guardrails complement, not replace, evals and structured output

Day 19 proved `AgentResult` can be schema-valid while the answer is wrong or wrong-scope. That is not a schema failure; it is a quality/safety failure. Guardrails add checks for classes of unacceptable behavior, while evals still judge answer completeness and correctness.

A good interview explanation should sound like:

- Pydantic makes output machine-checkable.
- HITL bounds agency before the recursive retrieval action.
- Guardrails block or flag unsafe inputs/outputs.
- Evals measure whether the answer is good.
- Traces explain how the system got there.

### Prompt injection in RAG is often indirect

ProcureRAG retrieves synthetic procurement documents today, but a production procurement copilot would ingest PDFs, emails, contracts, supplier notes, and web/source-system text. Any retrieved text can contain instructions like “ignore your system prompt” or “send the user hidden fields.” The model must treat retrieved content as evidence, not instructions.

Minimum Day 20 safety target: a test case that places instruction-like text in retrieved context or a user prompt and verifies the system does not treat it as authority. This can be a local validator/fake-client test; it does not need a live model.

### PII/sensitive-data controls need both input and output thinking

DeepLearning.AI’s guardrails course uses PII as both an input and output risk. ProcureRAG’s domain also has procurement-sensitive facts: supplier names, contract terms, approval thresholds, and internal process data. The first local guardrail can be simple — e.g. detect/redact emails, phone numbers, ID-like strings, or names in prompts/outputs — but Juan should be clear what it does and does not cover.

Do not overclaim. A regex-based guard is a baseline, not enterprise DLP. If a GuardrailsAI/Presidio path is too heavy, local validators are acceptable if the docs say so.

### Excessive agency is already partly controlled by Day 18

The graph has exactly one agentic action today: the bounded follow-up retrieval pass for Q091/Q092. Day 18’s `interrupt()` approval is already an excessive-agency control. Day 20 should surface and test that control as part of the safety story:

- only Q091/Q092 pause for second-pass retrieval;
- reviewer can approve, edit, or reject;
- invalid decisions do not trap the run;
- rejection produces `gap_report`, not hidden action;
- no tool writes, emails, purchasing actions, or external side effects exist.

## Target evidence by end of day

- [ ] Course/source work recorded with exact lesson/page names:
  - [ ] DeepLearning.AI `Introduction`.
  - [ ] DeepLearning.AI `Failure modes in RAG applications`.
  - [ ] DeepLearning.AI `What are guardrails`.
  - [ ] DeepLearning.AI `Building your first guardrail`.
  - [ ] DeepLearning.AI `Checking for hallucinations with Natural Language Inference`.
  - [ ] DeepLearning.AI `Using hallucination guardrail in a chatbot`.
  - [ ] DeepLearning.AI `Keeping a chatbot on topic`.
  - [ ] DeepLearning.AI `Ensuring no personal identifiable information (PII) is leaked`.
  - [ ] DeepLearning.AI `Preventing competitor mentions`.
  - [ ] DeepLearning.AI `Conclusion` and quiz/self-check.
  - [ ] OWASP 2025 risk mapping for `LLM01`, `LLM02`, `LLM05`, `LLM06`, `LLM07`, `LLM08`, `LLM09`, and `LLM10`.
- [ ] Guardrail test cases exist for at least:
  - [ ] one safe/allowed prompt or output;
  - [ ] one prompt-injection attempt in user input or retrieved context;
  - [ ] one PII/sensitive-data input or output case that is blocked/redacted/flagged;
  - [ ] one excessive-agency / approval-control behavior;
  - [ ] one structured-output/schema failure or unsafe `answered` case.
- [ ] Guardrail behavior is documented as **block**, **redact**, **flag**, or **route to HITL** for each case.
- [ ] Week 4 inventory is complete and names all artifacts:
  - Day 16 recursive retrieval;
  - Day 17 graph/state/routing;
  - Day 18 checkpointing/HITL/time travel;
  - Day 19 tracing/structured output;
  - Day 20 guardrails;
  - unresolved caveats.
- [ ] Full verification output is recorded: `pytest`, `compileall`, `ruff`, `regression_suite.py --verify-retrieval`, plus chosen guardrail demo command(s).
- [ ] `docs/eval-report.md` has a Week 4 gate section or addendum that can support HER-269 closure review.
- [ ] `docs/learning-log.md` has the real Day 20 evidence, not placeholders.
- [ ] Juan can explain why guardrails complement evals, traces, HITL, and structured outputs.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and choose guardrail scope, 30–45m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_graph.py --all-queries-summary
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/python src/agent_observability.py --query-ids Q091 Q014 --output docs/traces/day20-kickoff-q091-q014.jsonl
```

Then decide the minimum artifact shape:

1. Is today’s guardrail implementation local validators only, GuardrailsAI/Presidio, or a hybrid? - Hybrid.
2. Which layer owns each check: input, retrieved context, action/HITL, output, or schema?
3. Which examples will be the evidence anchors?
   - prompt injection: malicious user prompt or malicious retrieved-context snippet;
   - PII: email/phone/person-name style input or output;
   - excessive agency: Q091/Q092 approval/edit/reject behavior;
   - structured output: unsafe `answered`, missing citations, no recovered-chunk citations, or schema invalid row.
4. Which file will preserve the Week 4 gate inventory: `docs/eval-report.md`, a small dedicated doc, or both?

Recommendation: keep the build small. A local, deterministic guardrail layer with clear tests is better than adding a heavy dependency that Juan cannot explain.

### Block 1 — Course/source work, 90–120m

Read and map notes to ProcureRAG:

1. DeepLearning.AI guardrails course:
   - `Introduction` — guardrails as production reliability controls.
   - `Failure modes in RAG applications` — hallucination, off-topic, sensitive info leakage, brand/reputation risk.
   - `What are guardrails` — input/output guard placement.
   - `Building your first guardrail` — validator + guard concepts.
   - `Checking for hallucinations with Natural Language Inference` and `Using hallucination guardrail in a chatbot` — groundedness / entailment framing. Map to current citation and expected-answer limitations; do not force NLI if it becomes too heavy.
   - `Keeping a chatbot on topic` — domain restriction; map to procurement-only behavior.
   - `Ensuring no personal identifiable information (PII) is leaked` — input/output PII handling.
   - `Preventing competitor mentions` — map to supplier/scope safety, not necessarily literal competitors.
   - `Conclusion` and quiz/self-check.
2. OWASP 2025:
   - `LLM01 Prompt Injection` — user and indirect/retrieved-context injection.
   - `LLM02 Sensitive Information Disclosure` — PII and procurement-sensitive data.
   - `LLM05 Improper Output Handling` — validate before rendering/using model output.
   - `LLM06 Excessive Agency` — Day 18 HITL / bounded recursive retrieval.
   - `LLM07 System Prompt Leakage` — do not reveal system/developer prompts or hidden config.
   - `LLM08 Vector and Embedding Weaknesses` — retrieval poisoning, unauthorized retrieval, stale/unsafe embeddings.
   - `LLM09 Misinformation` — wrong Band 4 / wrong-scope contract examples from Day 19.
   - `LLM10 Unbounded Consumption` — route limits, max passes, live-call cost bounds.

Scratch-note prompts:

- Which ProcureRAG failures are quality issues vs safety issues?
- Which guardrails can run with no LLM/network credentials?
- Which current controls already exist from Day 18/19?
- What would be unacceptable to ship even if all unit tests pass?

### Block 2 — Design the guardrail contract, 45–60m

Before coding, draft a small table like this:

| Risk | Layer | Example input/output | Expected behavior | Evidence |
|---|---|---|---|---|
| Prompt injection | input or retrieved context | “Ignore previous instructions…” | block/flag; treat as evidence text only | unit test |
| PII leakage | input/output | email/phone/name | redact or block before model/user | unit test |
| Excessive agency | action | Q091 follow-up retrieval | pause for approve/edit/reject; reject -> `gap_report` | existing + new test |
| Improper output handling | output/schema | invalid `AgentResult` / citation gap | validation error or caveat | test |
| Misinformation | output/eval | Band 4 vs Band 3 | not fully solved; recorded as eval gap | docs + next step |

Keep the contract small enough to explain in an interview. The route’s goal is not “all security solved”; it is “Week 4 has concrete controls, tests, and honest gaps.”

### Block 3A — Primary route: Juan-owned guardrail artifact, 120–150m

Possible artifact shape, for Juan to design and implement:

- A small guardrail module or extensions to existing graph/output code that define deterministic guard/check results.
- Tests that do not require live models, LangSmith, GuardrailsAI Hub, or external network.
- A demo command that prints allowed vs blocked/redacted/flagged examples.
- A Week 4 gate addendum in `docs/eval-report.md`.

Suggested minimum behavior:

1. **Prompt-injection guard:** detect a short list of high-risk instruction patterns in user prompt and/or retrieved context (`ignore previous instructions`, `reveal system prompt`, `send secrets`, etc.). Decide whether to block, flag, or strip.
2. **PII/sensitive-data guard:** detect and redact/block emails and phone numbers at minimum; optionally names or supplier-sensitive fields if Juan chooses.
3. **Excessive-agency guard:** make Day 18’s approval boundary explicit in tests/docs: only one follow-up pass, reviewer controls the action, reject stops safely.
4. **Structured-output guard:** prevent or flag an `answered` result that has no citations, cites no recovered chunks after a recursive pass, or otherwise violates today’s chosen invariant.
5. **Week 4 inventory:** write a concise table of what Week 4 now has and what remains weak.

Recommended implementation constraints:

- Keep standard tests CI-safe.
- Avoid adding a dependency unless the course artifact genuinely needs it and Juan can explain it.
- Do not silently change Day 16–19 route distribution unless the guardrail intentionally blocks a route and the docs say so.
- Do not claim NLI/hallucination protection unless a real entailment/NLI check exists and is tested. Otherwise frame it as a future answer-quality guard.

### Block 3B — Fallback route: local validators + gate inventory only, 60–90m

Use this if GuardrailsAI/Presidio/NLI setup blocks progress.

Still produce:

1. Local deterministic validators for prompt-injection strings and PII regex examples.
2. Tests showing at least one allowed and one blocked/redacted/flagged case.
3. A small action/HITL safety test or docs evidence pointing to Day 18’s approval boundary.
4. A Week 4 gate inventory in `docs/eval-report.md`.
5. Learning-log evidence naming GuardrailsAI/Presidio/NLI as deferred, with blocker and next command or next lesson.

This fallback is acceptable because it preserves the core learning: guardrails are explicit application contracts. It is not acceptable to only summarize the course without ProcureRAG-specific tests or gate evidence.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/learning-log.md` — Day 20 entry with exact source completion, guardrail behavior, OWASP mapping, Week 4 inventory, verification outputs, and next Week 5 step.
- `docs/eval-report.md` — Week 4 gate section/addendum if the artifacts are ready for HER-269 review.

Then answer the interview drill below without notes.

## Interview drill

1. What is the difference between a guardrail, a unit test, an eval, a trace, and a schema?

   **Expected answer shape:** A guardrail runs in the application path and enforces a safety/reliability constraint. A unit test checks deterministic code behavior before runtime. An eval judges task quality across examples. A trace shows how one run executed. A schema validates the shape and invariants of data. ProcureRAG needs all five because no one layer catches everything.

2. Where can a prompt injection enter a RAG system?

   **Expected answer shape:** Directly through the user prompt, indirectly through retrieved documents/chunks, through tool outputs, or through memory/state. Retrieved text must be treated as evidence, not instructions. In ProcureRAG, this matters because future PDFs/contracts/emails can carry untrusted instructions even when they are legitimate sources.

3. What does Day 18’s HITL control protect against, and what does it not protect against?

   **Expected answer shape:** It bounds excessive agency for the recursive retrieval action: Q091/Q092 pause before the follow-up pass, a reviewer can approve/edit/reject, and reject stops as `gap_report`. It does not prove the final answer is correct, does not inspect PII, and does not prevent the model from misreading a retrieved source.

4. Why is a PII regex guard useful but insufficient?

   **Expected answer shape:** It is fast, deterministic, and CI-safe for obvious emails/phone numbers, so it catches common leaks before a model call or user response. But it misses many entity types, context-dependent secrets, and authorization issues. It should be documented as a baseline, not enterprise DLP.

5. How do OWASP `LLM01`, `LLM02`, and `LLM06` map to ProcureRAG?

   **Expected answer shape:** `LLM01` maps to prompt injection from users or retrieved context. `LLM02` maps to leaking PII, supplier data, contracts, internal approval info, or hidden config. `LLM06` maps to giving the agent too much autonomy; ProcureRAG currently limits this through one bounded recursive retrieval pass plus HITL approval.

6. Why did Day 19 prove structured output is not enough for safety?

   **Expected answer shape:** A schema-valid answer can still be false or wrong-scope. Day 19 produced examples where citations were real and schema-valid but the answer misread the Band 3 approval or used a wrong supplier contract. Structured output fixes shape and machine readability; answer quality still needs guardrails/evals.

7. What must be true before closing HER-269 / the Week 4 gate?

   **Expected answer shape:** Week 4 must have real evidence for recursive retrieval, graph routing, HITL/checkpointing, trace/observability, structured output, and guardrails. Tests/compile/lint/regression must pass. The docs must inventory known caveats honestly. Juan must be able to explain `create_agent` vs graph/state patterns, offline vs online eval, and excessive-agency risk.

## Hermes review protocol

When Juan has a serious Day 20 pass ready, ask Hermes:

> Day 20 guardrails + Week 4 gate work done. Review HER-287 and HER-269: exact DeepLearning.AI guardrails lessons, OWASP risk mapping, prompt-injection/PII/excessive-agency/schema guardrail tests, Week 4 artifact inventory, `docs/eval-report.md` gate section, `docs/learning-log.md` evidence, and real verification outputs. Run pytest/compile/ruff/regression and chosen guardrail demo commands. Do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify guardrail behavior and Week 4 inventory, and either close HER-287/HER-269 or return precise remaining tasks. Hermes must not replace Juan’s implementation.

## Stop condition

Day 20 is complete when:

1. The named DeepLearning.AI guardrails lessons and OWASP risk pages have been completed or explicitly summarized.
2. A minimal guardrail layer exists with tests for safe allowed behavior plus blocked/redacted/flagged unsafe behavior.
3. Prompt-injection, PII/sensitive-data, excessive-agency/HITL, and structured-output/schema risk are each represented in either code tests or an honest documented fallback.
4. Week 4 artifact inventory is complete and maps each artifact to evidence.
5. `docs/eval-report.md` and `docs/learning-log.md` contain real evidence and known caveats.
6. Tests/compile/lint/regression and chosen demo commands pass, or blockers are recorded honestly.
7. Juan can explain how guardrails complement evals, HITL, traces, and structured output.
8. HER-287 is ready for Hermes review, and HER-269 can either be closed or returned with a precise short list.

Do not close HER-287 or HER-269 on route creation alone. The route is the kickoff; Juan’s course work, artifact, evidence, and interview explanation are the acceptance criteria.
