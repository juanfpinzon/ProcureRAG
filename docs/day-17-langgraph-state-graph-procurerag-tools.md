# Day 17 — LangGraph State Graph + ProcureRAG Tool Boundaries

Date: 2026-09-28 kickoff.

Linear: HER-284 — Day 17 loop: LangGraph state graph + ProcureRAG tools.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

No new Boot.dev chapter today. Day 16 completed Boot.dev Chapter 11 (`Agentic` → `Recursive RAG`, `Agentic Search`) and produced the local recursive-retrieval experiment. Day 17 turns that experiment into an explicit graph/orchestration representation.

Primary source:

- **LangChain Academy — Foundation: Introduction to LangGraph - Python**: <https://academy.langchain.com/courses/intro-to-langgraph>
  - **Welcome to the course!**  - Completed
    - `Course Overview` - Completed
    - `Getting Set Up` - Completed
    - `Module 0 Resources` - Completed
  - **Module 1: Introduction** 
    - `Lesson 2: Simple Graph`        - Completed
    - `Lesson 4: Chain`- Completed
    - `Lesson 5: Router`- Completed
    - `Lesson 6: Agent`- Completed
    - `Lesson 7: Agent with Memory`- Completed
  - **Module 2: State and Memory**
    - `Lesson 1: State Schema` - Completed
    - `Lesson 2: State Reducers`- Completed
    - `Lesson 3: Multiple Schemas` - Completed

Companion / fallback sources:

- **LangChain Academy — Quickstart: LangGraph Essentials - Python**: <https://academy.langchain.com/courses/langgraph-essentials-python>
  - **Module 1: Course Overview**
    - `Lesson 1: Nodes`
    - `Lesson 2: Edges`
    - `Lesson 3: Conditional Edges`
    - `Lesson 4: Memory`
    - Optional if useful: `Lesson 5: Interrupt, Human in the Loop`, `Lesson 6: Application`
- **Hugging Face Agents Course — Unit 1: Introduction to Agents**: <https://huggingface.co/learn/agents-course/unit1/introduction>
  - Concepts to skim only: agents, tools/actions, and the `Think → Act → Observe` workflow.
- **Hugging Face Agents Course — Unit 2.3: The LangGraph framework**: <https://huggingface.co/learn/agents-course/unit2/langgraph/introduction>
  - `Introduction to LangGraph`
  - `What is LangGraph?`
  - `Building Blocks of LangGraph`
  - `Building Your First LangGraph`
  - Optional examples: `Document Analysis Graph`, quiz.

Exact source-note: the LangChain Academy public course page currently lists the Module 1 and Module 2 lesson names above. Individual lesson URLs may require enrollment/login, so navigate from the course page by module and lesson title.

## Day 17 objective

Represent ProcureRAG's retrieval/generation flow as a controlled state graph: explicit state, nodes, edges, conditional routing, and tool boundaries. The target is not “use LangGraph because agents are trendy.” The target is to make Day 16's measured recursive-retrieval contract explainable as orchestration: when the graph takes the normal retrieve→generate path, when it routes into a recursive/diagnostic path, what evidence moves through state, and where existing ProcureRAG functions are called as tools/nodes rather than rewritten.

By the end of the day, Juan should be able to whiteboard the ProcureRAG graph and explain the difference between a chain, router, graph, and agent using concrete Q001/Q005/Q091/Q092 examples.

## Starting state

Current repo evidence at kickoff:

- `src/agentic_retrieval.py` — Day 16 standalone recursive-retrieval experiment. It runs first-pass retrieval, evaluates missing docs/chunks, conditionally runs one targeted follow-up query, merges sources additively, and stops with named stop reasons.
- `tests/test_agentic_retrieval.py` — deterministic tests around trigger, merge, stop, no-second-pass controls, per-document Q092 reporting, and Q091 acceptable-chunk OR semantics.
- `src/generation.py` — source-cited generation path; current production entry point still uses single-pass retrieval and is not wired to the Day 16 recursive context.
- `src/reranking.py` — retrieval configs and `retrieval_config_for_query_type` boundary that Day 17 should reuse, not duplicate.
- `src/regression_suite.py` and `src/multi_doc_slice_eval.py` — evidence gates that keep Q091/Q092 behavior visible.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source. Do not create a duplicate `data/golden_queries.jsonl`.
- `pyproject.toml` currently includes `langchain-community` and `langchain-openai`, but no explicit `langgraph` dependency. If the course setup requires adding `langgraph`, Juan should decide and implement that change himself. If dependency/API setup blocks the day, use the fallback pure-Python graph simulation.

Baseline checks at kickoff:

```bash
./.venv/bin/pytest -q
# 218 passed in 4.26s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# frozen fixtures as_expected; current retrieval pipeline still matches every case's expectation
# Q091 remains visible in the frozen fixture lane as: term-level gap OPEN: missing ['Band 3']

./.venv/bin/python src/agentic_retrieval.py
# Q001, Q005: no_missing_evidence
# Q091: missing_chunk -> fixed_after_second_pass, POL-001::chunk-6 recovered
# Q092: missing_doc -> fixed_after_second_pass, CONTRACT-005 and POL-002 recovered

./.venv/bin/python src/multi_doc_slice_eval.py
# single-pass multi_doc slice unchanged: Q092 still misses CONTRACT-005/POL-002 under both configs
# this is expected because Day 16's recursive loop is not wired into the single-pass production path
```

Git status at kickoff was clean on `main` before this Day 17 route/log scaffold was added.

## Key concepts to nail today

### State is the contract between nodes

A graph is only as clear as the state passed between nodes. For ProcureRAG, state should not be a vague `dict` of whatever happened to be useful in one function. It should carry the evidence needed to explain and test decisions: original user query, matched `query_id`/`query_type` when known, retrieval config, retrieved source docs/chunks, missing-evidence diagnostics, chosen route, follow-up query when used, merged source list, answer/refusal if generation runs, and trace/debug notes.

A good state schema makes the interview story stronger: “Here is the object the graph updates; each node owns one transformation; the router reads these fields and chooses the next edge.”

### Nodes wrap existing ProcureRAG capabilities

Day 17 should not reimplement retrieval, reranking, generation, or eval. Those already exist. The graph layer should wrap them as nodes/tools:

- `retrieve_sources` node — calls the existing retrieval/reranking path.
- `diagnose_missing_evidence` node — reuses Day 16/eval helpers to identify missing docs/chunks/terms.
- `route_after_diagnosis` router — decides normal generation vs. recursive/diagnostic branch.
- `recursive_retrieve` node — calls or adapts the Day 16 recursive-retrieval contract.
- `generate_or_refuse` node — either calls the existing generation boundary or simulates it deterministically in tests.
- `finalize_trace` node — records route, stop reason, source IDs, caveats, and what was not attempted.

If Juan uses real LangGraph, these can become actual nodes/conditional edges. If setup blocks, a pure-Python graph runner with the same state and route tests is acceptable for today.

### Routers and conditional edges should be evidence-driven

The graph should route because a measured condition exists, not because a query “feels hard.” Day 16 already provides the right triggers:

- Q001 and Q005 controls: no missing evidence → normal path / no recursive retrieval.
- Q091: missing acceptable approval-band chunk → recursive/diagnostic path.
- Q092: missing primary documents → recursive/diagnostic path.

The router's output should be testable and named: `normal_generate`, `recursive_retrieve`, `refuse_or_report_gap`, or similarly precise route labels. Avoid hidden LLM judgment in the routing tests. The graph can support LLM-driven decisions later, but Day 17's interview value comes from deterministic control flow first.

### “Agent” does not have to mean open-ended autonomy

In this repo, an agentic graph should mean controlled orchestration with explicit state and stop conditions. A graph that always knows which nodes it may call, has one bounded recursive branch, and records stop reasons is much more credible than an open-ended tool-calling agent that can’t be evaluated.

Day 17's graph can be modest. It just needs to turn the measured Day 16 loop into a stateful orchestration layer that Juan can explain and test.

## Target evidence by end of day

- [ ] Course/source work recorded with exact lesson names:
  - [ ] LangChain Academy `Foundation: Introduction to LangGraph - Python` → Module 1 `Lesson 2: Simple Graph`, `Lesson 4: Chain`, `Lesson 5: Router`, `Lesson 6: Agent`, `Lesson 7: Agent with Memory`.
  - [ ] LangChain Academy Module 2 `State and Memory` → `Lesson 1: State Schema`, `Lesson 2: State Reducers`, `Lesson 3: Multiple Schemas`.
  - [ ] Optional/fallback: `Quickstart: LangGraph Essentials - Python` → `Nodes`, `Edges`, `Conditional Edges`, `Memory`.
  - [ ] Companion skim: Hugging Face Agents Course Unit 1 and Unit 2.3 LangGraph pages.
- [ ] A Juan-owned graph/orchestration artifact exists, likely `src/agent_graph.py` or equivalent.
- [ ] The artifact defines or documents a state schema carrying at least:
  - [ ] user query;
  - [ ] query id/type when known;
  - [ ] retrieval config / route label;
  - [ ] retrieved sources with doc IDs and chunk IDs;
  - [ ] missing-evidence diagnostics;
  - [ ] follow-up query / recursive-retrieval result when triggered;
  - [ ] generated answer/refusal or explicit “not generated” marker;
  - [ ] trace/debug notes and stop reason.
- [ ] Existing retrieval/eval/generation functions are reused through boundaries; the graph does not duplicate core retrieval implementation.
- [ ] Conditional routing covers at least:
  - [ ] a no-recursion control (Q001 or Q005);
  - [ ] a recursive/diagnostic route for Q091 or Q092;
  - [ ] an honest blocked/still-open route if a missing-evidence case cannot be fixed.
- [ ] Deterministic tests use fake retrieval/generation functions where possible, so routing is fast and CI-safe.
- [ ] Any real LangGraph dependency/API blocker is documented honestly; fallback simulation is acceptable if it preserves state/nodes/edges/router learning.
- [ ] Verification commands are run and copied into `docs/learning-log.md`.
- [ ] Juan can explain chain vs. router vs. graph vs. agent in the context of ProcureRAG.

## Recommended 6-hour split

### Block 0 — Reactivate Day 16 evidence and dependency baseline, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
./.venv/bin/python src/agentic_retrieval.py
```

Then inspect:

- `src/agentic_retrieval.py` — state fields already returned by `run_recursive_retrieval`.
- `tests/test_agentic_retrieval.py` — fake `retrieve_fn` injection pattern to copy for graph tests.
- `src/generation.py` — generation/source boundary, but do not force a live LLM call into tests.
- `src/reranking.py` — `retrieval_config_for_query_type`, `DEFAULT_RETRIEVAL_CONFIG`, `MULTI_DOC_RETRIEVAL_CONFIG`.
- `pyproject.toml` — confirm whether `langgraph` is present before writing imports.

Answer before coding:

1. Which Day 16 function already behaves like a graph node or mini-graph?
2. Which state fields are already present, and which are missing for an interview-ready graph trace?
3. Will today's artifact use real LangGraph, or a pure-Python state graph fallback first?

### Block 1 — LangGraph / agent-framework study, 75–105m

Primary path:

1. LangChain Academy `Foundation: Introduction to LangGraph - Python`:
   - Welcome/setup/resources as needed.
   - Module 1 `Introduction`: `Lesson 2: Simple Graph`, `Lesson 4: Chain`, `Lesson 5: Router`, `Lesson 6: Agent`, `Lesson 7: Agent with Memory`.
   - Module 2 `State and Memory`: `Lesson 1: State Schema`, `Lesson 2: State Reducers`, `Lesson 3: Multiple Schemas`.
2. Companion skim:
   - Hugging Face Agents Course Unit 1 `Introduction to Agents` for tools/actions and `Think → Act → Observe` vocabulary.
   - Hugging Face Agents Course Unit 2.3 `The LangGraph framework` → `Introduction to LangGraph`, `What is LangGraph?`, `Building Blocks of LangGraph`, `Building Your First LangGraph`.

Write scratch notes specifically mapping each term to ProcureRAG:

- state → what fields does ProcureRAG carry?
- node → which existing function does this node wrap?
- edge → what transition happens next?
- conditional edge/router → what evidence determines the branch?
- agent → what is allowed to act, and what is deliberately not allowed?

### Block 2 — Design the state schema and route table, 45–60m

Before writing code, draft the graph contract in notes or `docs/eval-report.md`:

| Graph field / route | Meaning | Q001/Q005 control | Q091 hard case | Q092 hard case |
|---|---|---|---|---|
| `query_id` / `query_type` | Known corpus query identity | Q001/Q005 | Q091 | Q092 |
| `sources` | current retrieval context | complete | doc complete, chunk incomplete | missing primary docs |
| `missing_evidence` | deterministic docs/chunks/terms gap | empty | `POL-001::chunk-5/6` absent | `CONTRACT-005`, `POL-002` absent |
| `route` | next graph edge | `normal_generate` / stop | `recursive_retrieve` | `recursive_retrieve` |
| `followup_query` | targeted action if routed | none | approval-band query | cleaning-contractor EDD query |
| `stop_reason` | final state | no missing evidence | fixed/still missing | fixed/still missing |

Keep the graph small enough to explain. A minimal version with three or four nodes and one conditional edge is better than a broad framework demo with unclear evidence.

### Block 3A — Primary route: Juan-owned graph artifact, 120–150m

Possible artifact shape, for Juan to design and write:

- `src/agent_graph.py` or equivalent.
- A typed or documented state schema, such as a `TypedDict`.
- Node functions that accept and return state, for example:
  - `retrieve_node(state, retrieve_fn=...)`
  - `diagnose_node(state, evidence_fn=...)`
  - `route_after_diagnosis(state) -> route label`
  - `recursive_retrieve_node(state, recursive_fn=...)`
  - `generate_or_finalize_node(state, generation_fn=...)`
- A graph invocation function for a query row or user query.
- Tests that inject fake retrieval/generation functions and assert the route labels, state updates, and stop reasons.

Recommended behavior:

1. Run normal retrieval or fake retrieval into state.
2. Diagnose missing evidence using existing Day 16/eval helpers where possible.
3. Route:
   - no missing evidence → normal path / no recursive pass;
   - missing doc/chunk and follow-up available → recursive path;
   - missing evidence but no safe follow-up → report gap/refusal path.
4. Preserve trace evidence: docs/chunks before, route taken, docs/chunks after, stop reason.
5. Keep live LLM calls out of unit tests. If generation is included, fake it in tests and make live smoke optional.

### Block 3B — Fallback route: pure-Python graph simulation, 60–90m

Use this if LangGraph installation/API setup blocks the day.

Still produce:

1. The same state schema.
2. The same node functions and route labels.
3. A small pure-Python runner that executes nodes in order and uses a router function for the conditional edge.
4. Deterministic tests proving Q001/Q005 do not recurse and Q091/Q092 route into the recursive branch.
5. A docs note explaining exactly what blocked real LangGraph wiring and what remains for the next day.

This fallback is acceptable if it preserves the core learning: state, nodes, edges, conditional routing, and tool boundaries. It is not acceptable to replace the day with more retrieval tuning.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/eval-report.md` — Day 17 addendum if the graph produces meaningful routing/trace evidence beyond unit tests.
- `docs/learning-log.md` — Day 17 entry with course notes, state schema, route table, verification outputs, and what remains weak.

Then answer the interview drill below without notes.

## Interview drill

1. What is the difference between a chain and a graph in LangGraph terms?

   **Expected answer shape:** A chain is usually a fixed sequence of steps. A graph is explicit state plus nodes connected by edges, including conditional edges that can route based on state. ProcureRAG needs a graph once retrieval can branch into normal generation, recursive retrieval, or refusal/gap reporting.

2. What fields belong in ProcureRAG's graph state, and why?

   **Expected answer shape:** user query, query id/type, retrieval config, sources with doc/chunk IDs, missing-evidence diagnostics, route label, follow-up query, answer/refusal, trace notes, and stop reason. These fields let the graph make decisions and let reviewers audit why it took a branch.

3. How is the Day 16 recursive-retrieval loop already graph-shaped?

   **Expected answer shape:** It has state, a first retrieval node, an evidence-diagnosis node, a router/trigger decision, an optional second retrieval node, a merge node, and a final stop reason. Day 17 makes that structure explicit and reusable rather than hidden inside one function.

4. Why should the graph reuse existing retrieval/generation functions instead of rewriting them?

   **Expected answer shape:** The repo already has tested retrieval, reranking, generation, and eval boundaries. The graph's job is orchestration and traceability, not inventing another retrieval implementation. Reuse prevents drift and keeps evidence comparable to prior days.

5. What makes a router safe enough for this learning repo?

   **Expected answer shape:** deterministic trigger signals, named route labels, no hidden live-LLM judgment in unit tests, controls that prove no unnecessary recursion, hard stop conditions, and evidence captured before/after each branch.

6. When is a pure-Python graph simulation acceptable instead of real LangGraph?

   **Expected answer shape:** When dependency/API setup would consume the day, as long as the simulation preserves the learning contract: explicit state schema, nodes, edges, conditional routing, deterministic tests, and a clear next step for real LangGraph wiring. It should not become generic retrieval work.

## Hermes review protocol

When Juan has a serious Day 17 pass ready, ask Hermes:

> Day 17 LangGraph/state-graph artifact done. Review HER-284: exact LangGraph/HF lesson notes, state schema, node/tool boundaries, conditional routing, deterministic tests, route traces for Q001/Q005 and Q091/Q092, verification outputs, and learning-log evidence. Verify pytest/compile/ruff/regression gates and do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify the evidence, and either close HER-284 or return precise remaining tasks. Hermes must not replace Juan's implementation.

## Stop condition

Day 17 is complete when:

1. The named LangChain Academy / Hugging Face source lessons have been completed or explicitly reviewed and summarized.
2. A graph/state artifact exists or a clearly documented pure-Python fallback exists.
3. The state schema is explicit enough to explain in an interview.
4. Existing ProcureRAG retrieval/eval/generation boundaries are reused rather than duplicated.
5. Conditional routing is tested on at least one clean control and one hard case.
6. Tests/compile/lint and relevant retrieval gates pass, or blockers are recorded honestly.
7. `docs/learning-log.md` is updated with real evidence, not imagined output.
8. Juan can explain chain vs. router vs. graph vs. agent using ProcureRAG-specific examples.

Do not close HER-284 on route creation alone. The route is the kickoff; Juan's course work, graph artifact, evidence, and interview explanation are the acceptance criteria.
