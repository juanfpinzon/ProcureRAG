# Day 18 — Agent Memory, HITL, Observability, and Current Agent APIs

Date: 2026-10-02 kickoff.

Linear: HER-285 — Day 18 loop: agent memory, HITL, and current create_agent APIs.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

No new Boot.dev chapter today. Day 16 completed Boot.dev Chapter 11 (`Agentic` → `Recursive RAG`, `Agentic Search`), and Day 17 completed the first LangGraph state-graph artifact. Day 18 adds the **control plane** around that graph: memory/checkpointing, human approval/interrupts, observability, and API-current LangChain agent vocabulary.

Primary source:

- **LangChain Academy — Foundation: Introduction to LangGraph - Python**: <https://academy.langchain.com/courses/intro-to-langgraph>
  - **Module 2: State and Memory**
    - `Lesson 4: Trim and Filter Messages` - Completed
    - `Lesson 5: Chatbot w/ Summarizing Messages and Memory` - Completed
    - `Lesson 6: Chatbot w/ Summarizing Messages and External Memory` - Completed
  - **Module 3: UX and Human-in-the-Loop**
    - `Lesson 1: Streaming` - Completed
    - `Lesson 2: Breakpoints` - Completed
    - `Lesson 3: Editing State and Human Feedback` - Completed
    - `Lesson 4: Dynamic Breakpoints` - Completed
    - `Lesson 5: Time Travel` - Completed
  - **Module 5: Long-Term Memory**
    - `Lesson 1: Short vs. Long-Term Memory` - Completed
    - `Lesson 2: LangGraph Store` - Completed
    - `Lesson 3: Memory Schema + Profile` - Completed
    - `Lesson 4: Memory Schema + Collection` - Completed
    - `Lesson 5: Build an Agent with Long-Term Memory` - Completed

API-current companion sources:

- **LangChain v1 release notes — `create_agent`**: <https://docs.langchain.com/oss/python/releases/langchain-v1.md>
  - `create_agent` is the LangChain 1.x standard agent factory.
  - Middleware is the v1 control surface for dynamic prompts, summarization, state management, guardrails, and human approval flows.
- **LangChain middleware overview**: <https://docs.langchain.com/oss/python/langchain/middleware/overview>
  - Middleware runs inside the compiled LangGraph returned by `create_agent`.
  - A middleware-enabled `create_agent` can be embedded as a node/subgraph in a larger `StateGraph`.
- **LangChain prebuilt middleware**: <https://docs.langchain.com/oss/python/langchain/middleware/built-in>
  - `HumanInTheLoopMiddleware` pauses sensitive tool calls for approval/edit/rejection and requires a checkpointer.
  - `SummarizationMiddleware` compresses long conversation history near token limits.
  - `PIIMiddleware` redacts or blocks sensitive data before/after model/tool paths.
- **LangGraph checkpointers**: <https://docs.langchain.com/oss/python/langgraph/checkpointers>
  - Checkpointers persist graph state by `thread_id` and enable memory, HITL resumption, time travel, and fault tolerance.
- **LangGraph time travel**: <https://docs.langchain.com/oss/python/langgraph/use-time-travel>
  - Replay resumes from checkpoints; nodes after the checkpoint re-execute.
- **LangSmith tracing for LangGraph**: <https://docs.langchain.com/langsmith/trace-with-langgraph>
  - `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` enable tracing for LangGraph/LangChain runs.
- **`create_react_agent` reference / deprecation note**: <https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent>
  - `langgraph.prebuilt.create_react_agent` is deprecated in favor of `langchain.agents.create_agent`.

Exact source-note: LangChain Academy may require enrollment/login for individual lesson pages. Use the course page/module menu for the lesson names above. The public LangChain docs currently state that `create_agent` is the standard v1 agent builder, and that `create_react_agent` is deprecated/migration-context material.

## Day 18 objective

Turn Day 17's graph from “a working orchestration artifact” into “a controlled, observable agentic system.” The goal is not to add more agent framework surface area for its own sake. The goal is for Juan to explain how a production RAG agent avoids silent autonomy: it records what happened, pauses before high-impact actions, can resume from state, can replay/fork a run, and uses current LangChain APIs intentionally instead of copying stale `create_react_agent` examples.

By the end of the day, Juan should be able to answer: “If ProcureRAG routes into a recursive retrieval pass or a gap-report path, what state is saved, who can inspect/approve it, how do we replay it, and when would we use low-level LangGraph vs `create_agent` middleware?”

## Starting state

Current repo evidence at kickoff:

- `src/agent_graph.py` — Day 17 LangGraph `StateGraph` over Day 16 recursive retrieval: `retrieve → diagnose → route_after_diagnosis → {generate | recursive_retrieve → diagnose | report_gap}`.
- `tests/test_agent_graph.py` — 14 deterministic tests covering graph structure, router behavior, recursion-limit safety, Q091/Q092 recursive paths, `report_gap`, fake-client generation, and Day 16 parity.
- `src/agentic_retrieval.py` — Day 16 recursive-retrieval experiment and `AGENTIC_CASE_OVERRIDES` for Q091/Q092.
- `src/generation.py` — source-cited generation boundary; single-pass `generation.main()` is still not wired to the Day 17 graph.
- `src/regression_suite.py` — still reports Q091's frozen fixture `Band 3` gap open because the graph path is not wired into this suite.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query labeled set. Do not create a duplicate `data/golden_queries.jsonl`.
- `pyproject.toml` already includes `langgraph>=1.2.11`, `langchain>=1.4.0`, `langchain-core>=1.6.3`, `langchain-openai>=1.6.2`, and `langchain-openrouter>=0.2.9`.

Baseline checks at kickoff:

```bash
./.venv/bin/pytest -q
# 232 passed in 2.85s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# all 7 frozen cases as_expected; current retrieval pipeline still matches every case's expectation
# Q091 frozen fixture lane still shows: term-level gap OPEN: missing ['Band 3']
```

Git status at kickoff was clean on `main` before this Day 18 route/log scaffold was added.

## Key concepts to nail today

### Checkpointing is not “memory” by itself, but it is the foundation

A LangGraph checkpointer saves state snapshots at super-step boundaries, keyed by a thread. That enables three things ProcureRAG now needs: resuming after a human approval, replaying a run from a known state, and inspecting what state fields existed before/after the graph routed into a second retrieval pass.

For Day 18, avoid vague “the agent remembers things” language. Say exactly which state is saved: query id/type, route history, diagnoses, source docs/chunks, follow-up query, answer/gap report, and stop reason. Then separate **short-term thread memory** (state within a run/thread) from **long-term memory/store** (facts or preferences intentionally retained across threads). ProcureRAG likely needs the first now; the second is a future product decision, not an automatic good.

### HITL is a control point, not a UI flourish

The Day 17 graph has one high-impact branch: accepting a second retrieval pass or deciding to answer/report a gap after incomplete evidence. In a procurement copilot, the analogous production actions could include exporting evidence, sending an answer to a business user, or accepting a low-confidence response. A HITL point should make the system pause with enough state for a reviewer to approve, edit, or reject.

For today's artifact, Juan does not need to build a polished UI. A deterministic approval interface or LangGraph interrupt/checkpointer demo is enough if it proves the control concept and is covered by tests.

### Observability should explain the route, not just log that something happened

Day 17 already prints route distribution: 76 direct `generate`, 2 `recursive_retrieve → generate`, 15 `report_gap`. Day 18 should turn this into inspectable trace evidence. For Q091/Q092, a useful trace shows:

- first-pass route and missing-evidence signal;
- which follow-up query ran;
- which chunks/documents entered state after the follow-up;
- why the router stopped;
- whether the final answer was generated, blocked, or reported as a gap.

LangSmith tracing is a natural fit if credentials are available. If not, a local trace artifact or printed trace table is acceptable today. Do not block the learning day on SaaS setup.

### `create_agent` is the current agent factory; low-level `StateGraph` still has a role

LangChain v1 positions `langchain.agents.create_agent` as the standard agent factory. It returns a LangGraph-backed agent and uses middleware for production controls: summarization, PII handling, human approval, retries, call limits, and custom hooks. The older `langgraph.prebuilt.create_react_agent` pattern should be treated as deprecated or migration-context material.

ProcureRAG can still use a hand-written `StateGraph` for the Day 17 graph because the topology is deliberately narrow and evidence-driven. The API decision to document today is not “one API wins forever.” It should be something like:

- Use low-level `StateGraph` for deterministic retrieval orchestration where route labels and eval-state fields must be explicit.
- Use `create_agent` when the artifact is a tool-calling model loop with middleware controls (HITL, summarization, PII, tool-call limits) and current LangChain compatibility matters.
- A `create_agent` can later be embedded as a node/subgraph inside a larger StateGraph if ProcureRAG needs both patterns.

## Target evidence by end of day

- [ ] Course/source work recorded with exact lesson names:
  - [ ] LangChain Academy Module 2 `State and Memory` → `Trim and Filter Messages`, `Chatbot w/ Summarizing Messages and Memory`, `Chatbot w/ Summarizing Messages and External Memory`.
  - [ ] LangChain Academy Module 3 `UX and Human-in-the-Loop` → `Streaming`, `Breakpoints`, `Editing State and Human Feedback`, `Dynamic Breakpoints`, `Time Travel`.
  - [ ] LangChain Academy Module 5 `Long-Term Memory` → `Short vs. Long-Term Memory`, `LangGraph Store`, `Memory Schema + Profile`, `Memory Schema + Collection`, `Build an Agent with Long-Term Memory`.
  - [ ] LangChain v1 docs for `create_agent`, middleware, HITL, PII, summarization, checkpointers, and `create_react_agent` deprecation.
- [ ] A Juan-owned decision note exists, likely in `docs/eval-report.md`, a new `docs/day-18-*` addendum, or a small dedicated doc, explaining low-level `StateGraph` vs `create_agent` for ProcureRAG.
- [ ] A memory/checkpointing/resumable-state artifact exists or is explicitly scoped, with tests or a reproducible demo.
- [ ] A HITL/approval point exists for at least one agentic decision, or a deterministic fake approval interface exists with a clear migration path to LangGraph/LangChain built-ins.
- [ ] Trace evidence exists for Q091/Q092 showing route, before/after state, added sources/chunks, and stop reason.
- [ ] The 76 / 2 / 15 all-query route distribution is preserved as the Day 18 observability baseline unless Juan intentionally changes policy.
- [ ] The `report_gap` policy for the 15 gapped non-override queries is decided or recorded as an open decision: refuse vs. caveated answer vs. add more follow-up strategies.
- [ ] Streaming, breakpoints, editing state, dynamic breakpoints, and time travel are either demonstrated minimally or documented as deliberate deferrals with reasons.
- [ ] Verification commands are run and copied into `docs/learning-log.md`.
- [ ] Juan can explain why memory/HITL/checkpoints reduce excessive-autonomy risk without pretending they solve answer completeness.

## Recommended 6-hour split

### Block 0 — Reactivate Day 17 graph and baseline, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
./.venv/bin/python src/agent_graph.py
./.venv/bin/python src/agent_graph.py --all-queries-summary
```

Then inspect:

- `src/agent_graph.py` — state schema, route labels, `trace`, `diagnoses`, and existing observability note.
- `tests/test_agent_graph.py` — fake retrieval/client pattern to reuse for HITL/checkpoint tests.
- `src/agentic_retrieval.py` — Day 16 follow-up policy and `AGENTIC_CASE_OVERRIDES`.
- `src/generation.py` — live generation boundary and citation validation.
- `pyproject.toml` — confirm current LangChain/LangGraph dependencies.

Answer before coding:

1. What state fields must be visible to approve or reject a recursive pass?
2. Is today's memory/checkpointing artifact thread-level persistence, long-term store memory, or both?
3. Is today's HITL control protecting a retrieval action, an answer/export action, or a tool call?
4. Where should the current-API decision live so a future reviewer sees it?

### Block 1 — Course/source work, 90–120m

Primary:

1. LangChain Academy Module 2 `State and Memory`:
   - `Lesson 4: Trim and Filter Messages`
   - `Lesson 5: Chatbot w/ Summarizing Messages and Memory`
   - `Lesson 6: Chatbot w/ Summarizing Messages and External Memory`
2. Module 3 `UX and Human-in-the-Loop`:
   - `Lesson 1: Streaming`
   - `Lesson 2: Breakpoints`
   - `Lesson 3: Editing State and Human Feedback`
   - `Lesson 4: Dynamic Breakpoints`
   - `Lesson 5: Time Travel`
3. Module 5 `Long-Term Memory`:
   - `Lesson 1: Short vs. Long-Term Memory`
   - `Lesson 2: LangGraph Store`
   - `Lesson 3: Memory Schema + Profile`
   - `Lesson 4: Memory Schema + Collection`
   - `Lesson 5: Build an Agent with Long-Term Memory`

Companion:

1. LangChain v1 release notes: `create_agent` and middleware.
2. Middleware overview: how `create_agent` middleware lives inside a compiled LangGraph and can be embedded in a larger `StateGraph`.
3. Prebuilt middleware: `HumanInTheLoopMiddleware`, `SummarizationMiddleware`, `PIIMiddleware`, model/tool-call limits.
4. LangGraph checkpointers and time travel.
5. LangSmith tracing for LangGraph.
6. `create_react_agent` deprecation/migration note.

Write scratch notes mapping every concept to ProcureRAG:

- checkpointer → what thread/run state should ProcureRAG persist?
- breakpoint/interrupt → which node/action should pause?
- edit state → what would a reviewer be allowed to change?
- time travel → which checkpoint would be useful to replay for Q091/Q092?
- store/long-term memory → what, if anything, is safe to retain beyond one run?
- `create_agent` middleware → which middleware would apply to a procurement copilot and why?

### Block 2 — Design the control-plane contract, 45–60m

Draft a decision table before coding:

| Control concept | ProcureRAG use | Today’s minimum artifact | Future production version |
|---|---|---|---|
| Checkpoint/thread memory | Preserve `agent_graph` state for Q091/Q092 and resume after approval | `InMemorySaver` or fake checkpointer demo with thread ids | durable checkpointer / Agent Server |
| HITL approval | Pause before recursive pass or before final answer/export when evidence is incomplete | deterministic approval function or LangGraph interrupt | `HumanInTheLoopMiddleware` / UI approval queue |
| Time travel | Replay from before `recursive_retrieve` to test alternate follow-up query | documented or minimal `get_state_history` demo | trace-driven debugging workflow |
| Observability | Show route, missing evidence, added chunks, stop reason | local trace table and/or LangSmith trace link/id | LangSmith project with tagged runs |
| Current agent API | Avoid stale `create_react_agent` examples | docs note: low-level graph vs `create_agent` | `create_agent` node/subgraph with middleware |

Keep the artifact small. A focused checkpoint/HITL wrapper around the existing Day 17 graph is better than a generic toy chatbot that teaches nothing about Q091/Q092.

### Block 3A — Primary route: Juan-owned control-plane artifact, 120–150m

Possible artifact shape, for Juan to design and write:

- A docs decision note, for example a Day 18 section in `docs/eval-report.md` or a new `docs/agent-control-plane.md`.
- A small module or extension around `src/agent_graph.py`, if needed, that demonstrates one of:
  - compiling the existing graph with an `InMemorySaver` checkpointer and invoking it with a `thread_id`;
  - a HITL approval function that receives `{query_id, route, missing_evidence, proposed_followup_query}` and returns approve/reject/edit;
  - an interrupt/breakpoint pattern that pauses before `recursive_retrieve` or before `generate`.
- Tests that use fake retrieval/client/approval functions. Do not require live LangSmith or live LLM in the standard test suite.
- A CLI/demo command that prints trace/control evidence for Q091/Q092.

Recommended behavior:

1. Preserve Day 17 route outputs unchanged for Q001/Q005/Q091/Q092 unless intentionally changing policy.
2. Make the approval state inspectable: first-pass missing evidence, proposed follow-up query, source counts, and risk/cost note.
3. If approved, continue to recursive retrieval and re-diagnose.
4. If rejected, route to `report_gap` or another explicit stop reason.
5. If edited, use the edited follow-up query and record that it was edited.
6. Keep the live LLM optional. HITL/checkpoint tests should be deterministic and fast.

### Block 3B — Fallback route: docs-first + fake checkpointer/HITL, 60–90m

Use this if LangGraph interrupt/checkpointer APIs or LangSmith credentials block the primary route.

Still produce:

1. The current-API decision note (`StateGraph` vs `create_agent`, `create_react_agent` deprecated/migration context).
2. A fake but deterministic checkpoint/resume or approval interface in tests or docs.
3. A trace table for Q091/Q092 using existing `state["trace"]`, `state["diagnoses"]`, and `route_history`.
4. A clear migration path to real `InMemorySaver`, `interrupt`, LangSmith tracing, and/or `HumanInTheLoopMiddleware`.

This fallback is acceptable if it preserves the learning: a control plane that makes state inspectable and decisions interruptible. It is not acceptable to skip the ProcureRAG mapping and only summarize docs.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/learning-log.md` — Day 18 entry with exact course lessons, API-current decision, memory/checkpoint artifact, HITL approval point, trace evidence, verification output, and remaining weakness.
- `docs/eval-report.md` or a new control-plane doc — only if the artifact produces route/trace/control evidence worth preserving outside the learning log.

Then answer the interview drill below without notes.

## Interview drill

1. What is the difference between checkpointing, short-term memory, and long-term memory?

   **Expected answer shape:** Checkpointing saves graph state at execution boundaries so a run can resume/replay. Short-term memory is thread/conversation/run context used within or across turns of one thread. Long-term memory/store persists selected facts across threads. ProcureRAG needs checkpointing for HITL/resume now; long-term memory needs a deliberate schema and retention policy.

2. Why does HITL need a checkpointer?

   **Expected answer shape:** An interrupt pauses execution after state has been saved. The reviewer inspects/approves/edits/rejects, then the graph resumes from the checkpoint. Without saved state, approval cannot safely continue the exact run.

3. Where would you put a human approval point in the Day 17 graph, and why?

   **Expected answer shape:** Before `recursive_retrieve` (approve the second pass and follow-up query) or before `generate`/export when evidence is incomplete or high-impact. For Q091/Q092, approve the targeted second pass because it changes the retrieval context and roughly doubles sources; for `report_gap`, approve whether to refuse vs. give a caveated answer.

4. What does LangSmith tracing add beyond the local `trace` list?

   **Expected answer shape:** Local trace lines are useful and testable, but LangSmith gives a structured run tree with node/tool/model spans, inputs/outputs, latency/tokens, errors, metadata/tags, and a UI for debugging/replay. For ProcureRAG, it should show route, missing evidence, follow-up query, added chunks, stop reason, and generation call if present.

5. Why is `create_agent` the current API, and why might ProcureRAG still keep a hand-written `StateGraph`?

   **Expected answer shape:** LangChain v1 recommends `create_agent` for tool-calling agents and exposes middleware for HITL, summarization, PII, retries, and limits. `create_react_agent` is deprecated/migration context. ProcureRAG's Day 17 graph is a custom deterministic workflow, so low-level `StateGraph` is appropriate; a `create_agent` can later be embedded as a node/subgraph when we need a model-driven tool loop with middleware.

6. Why is memory dangerous in a procurement copilot?

   **Expected answer shape:** Memory can preserve stale facts, leak sensitive supplier/procurement information, contaminate future queries with another user's context, and make answers depend on hidden state rather than auditable evidence. Memory needs schema, retention, redaction/PII policy, thread boundaries, and evidence-first prompting.

7. What is the right policy for the 15 `report_gap` queries found on Day 17?

   **Expected answer shape:** Not “just answer anyway” by default. Options: refuse/report the missing evidence, allow a human-approved caveated answer, or add more targeted follow-up strategies. The choice should be recorded as a product/eval decision because it changes user behavior and answer-risk posture.

## Hermes review protocol

When Juan has a serious Day 18 pass ready, ask Hermes:

> Day 18 memory/HITL/current-agent-API work done. Review HER-285: exact LangGraph Academy lesson notes, create_agent vs create_react_agent decision, checkpoint/memory artifact, HITL approval point, trace evidence for Q091/Q092, report_gap policy, tests, verification outputs, and learning-log evidence. Verify pytest/compile/ruff/regression gates and do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify the evidence, and either close HER-285 or return precise remaining tasks. Hermes must not replace Juan's implementation.

## Stop condition

Day 18 is complete when:

1. The named LangChain Academy modules/lessons and LangChain v1 docs have been completed or explicitly reviewed and summarized.
2. A current-API decision is recorded: low-level `StateGraph` vs `create_agent` vs both; `create_react_agent` is treated as deprecated/migration context.
3. A checkpointing/memory/resumable-state example exists or the fallback is documented with a clear migration path.
4. A HITL/approval point exists or a deterministic fake approval interface exists, with tests.
5. Trace evidence exists for Q091/Q092 showing before/after state, added chunks/docs, route, and stop reason.
6. The 15-query `report_gap` policy is decided or explicitly left open with a next signal.
7. Tests/compile/lint/regression gates pass, or blockers are recorded honestly.
8. `docs/learning-log.md` is updated with real evidence, not imagined output.
9. Juan can explain memory/HITL/checkpoints and API-current agent design using ProcureRAG-specific examples.

Do not close HER-285 on route creation alone. The route is the kickoff; Juan's course work, artifact, evidence, and interview explanation are the acceptance criteria.
