# Day 16 — Recursive RAG Pass for Q091/Q092 Gaps

Date: 2026-09-25 kickoff.

Linear: HER-283 — Day 16 loop: Recursive RAG pass for Q091/Q092 gaps.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **Chapter 11 — Agentic**
  1. **Recursive RAG** — use a second retrieval pass when first-pass evidence is incomplete.
  2. **Agentic Search** — use a bounded decision loop to choose whether to reformulate, retrieve again, or stop.

Companion sources for vocabulary only, not a framework mandate:

- **LangChain Academy landing page:** <https://academy.langchain.com/> — use this if the course UI changes or if you need to search all current Academy courses.
- **Primary companion course: Foundation: Introduction to LangGraph - Python:** <https://academy.langchain.com/courses/intro-to-langgraph>
  - **Module 1: Introduction** — navigate inside the course page after enrolling.
    - **Lesson 1: Motivation**
    - **Lesson 2: Simple Graph**
    - **Lesson 5: Router**
    - **Lesson 6: Agent**
    - Optional stretch: **Lesson 7: Agent with Memory** only if today's loop already works without it.
  - **Why this course:** the Academy page describes it as the basics of LangGraph for agentic and multi-agent applications, with more precision/control than black-box agent frameworks. That vocabulary maps directly to Day 16's bounded recursive-retrieval loop.
- **Fallback / faster navigation course: Quickstart: LangGraph Essentials - Python:** <https://academy.langchain.com/courses/langgraph-essentials-python>
  - **Module 1: Course Overview**
    - **Lesson 1: Nodes**
    - **Lesson 2: Edges**
    - **Lesson 3: Conditional Edges**
    - **Lesson 4: Memory**
    - Optional: **Lesson 6: Application** if you want a small applied workflow example.
  - **When to use this instead:** if the Foundation course is hard to find in the Academy UI, use this Quickstart course to learn the exact state/node/edge/conditional-edge vocabulary needed for the Day 16 contract. It is shorter and more navigation-friendly.
- **LangGraph docs overview:** <https://docs.langchain.com/oss/python/langgraph/overview> — use this for concepts of explicit state, nodes, conditional edges, and deterministic control flow. Do not let framework setup replace the core ProcureRAG experiment.

Navigation note: LangChain Academy exposes stable public URLs for courses, but not always for individual lessons/modules before enrollment. The links above intentionally point to the course pages; once inside, use the listed module and lesson names.

Exact source-note: Boot.dev's public course page confirms Chapter 11 is **Agentic** and describes it as agents that iteratively refine queries and navigate retrieval workflows. HER-283 and Day 15's route name the two Chapter 11 lesson titles above; use those exact titles in the learning log.

## Day 16 objective

Turn Day 15's measured Week 3 gaps into the first small Week 4 agentic retrieval experiment. The goal is not to build a generic chat agent. The goal is to prove that ProcureRAG can detect a first-pass retrieval weakness, make a targeted second retrieval attempt, and report whether the missing evidence actually reached context.

Two cases anchor the day:

1. **Q091** — first-pass and repaired `multi_doc` retrieval now bring `POL-001` into context, but not the exact `POL-001::chunk-4` approval-band threshold chunk needed for the answer to state `Band 3`. The current suite keeps this visible as `term-level gap OPEN: missing ['Band 3']`.
2. **Q092** — both default and repaired configs still miss `CONTRACT-005` and `POL-002`. Day 15 diagnosed two causes: `CONTRACT-005` is found by first-stage retrieval but demoted by the reranker; `POL-002` is weaker in first-stage/fusion and still not promoted into generation context even under a deeper diagnostic pool.

By the end of the day, Juan should have a minimal recursive-retrieval contract that says: when do we trigger a second pass, what reformulation do we run, what changed in the evidence, and when do we stop?

## Starting state

Current repo evidence at kickoff:

- `src/generation.py` — source-cited answer path; real entry point uses `retrieval_config_for_query_type(query_row["query_type"])` so `multi_doc` queries get the wider/deeper config.
- `src/reranking.py` — `DEFAULT_RETRIEVAL_CONFIG` (`pool_size=15`, `top_k=5`, no diversity cap), `MULTI_DOC_RETRIEVAL_CONFIG` (`pool_size=80`, `top_k=10`, `max_chunks_per_document=2`), and `retrieval_config_for_query_type`.
- `src/regression_suite.py` — frozen-fixture lane plus `--verify-retrieval` current-pipeline lane. Q091 still has an expected missing term: `Band 3`.
- `src/multi_doc_slice_eval.py` — full 5-query `multi_doc` slice comparison across default and repaired configs.
- `docs/eval-report.md` and `docs/learning-log.md` — Day 15 gate evidence says Week 3 is ready for closure, with Q091/Q092 as the first Week 4 targets.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source; do not create a duplicate `data/golden_queries.jsonl`.

Baseline checks at Day 16 kickoff:

```bash
./.venv/bin/pytest -q
# 206 passed in 4.88s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# 7/7 frozen fixture cases as_expected; 6/6 current retrieval-pipeline checks [OK]
# Q091 remains intentionally visible as: term-level gap OPEN: missing ['Band 3']

./.venv/bin/python src/multi_doc_slice_eval.py
# default-config multi_doc P@1 sanity check: 0.600
# Q005 fine; Q016 chunk gap addressed; Q091 missing docs fixed but Band 3 term gap remains;
# Q092 still missing CONTRACT-005 and POL-002; Q093 fixed
```

Git status at kickoff was clean on `main` before the Day 16 route/log docs were added.

## Key concepts to nail today

### Recursive RAG is a measured retry, not “ask the model again”

Recursive RAG should start with a specific failure signal. In ProcureRAG that signal can be deterministic: a missing primary document, a missing required chunk, a missing required term in the answer, or a low-confidence / suspicious reranker outcome. The second pass should be a targeted retrieval action, not a vague prompt like “try harder.”

For Q091, the first-pass signal is: `POL-001` reaches context, but `Band 3` is still absent from the answer and the known threshold-bearing chunk is not in context. A useful second pass should reformulate toward approval-band thresholds: e.g. “approval bands EUR 50,000 250,000 Band 3 VP Procurement”. The evidence of success is not nicer prose; it is `POL-001::chunk-4` reaching context and/or the expected `Band 3` term no longer missing.

For Q092, the first-pass signal is different. `CONTRACT-005` is not a pool-depth miss in the same way: Day 15 found BM25 can see it, but the reranker ranks it too low for generation context. `POL-002` has a weaker first-stage/fusion signal and still fails after deeper diagnostic retrieval. A good recursive loop may need to report these as separate failure owners rather than pretending one reformulation fixes both.

### Agentic means bounded control flow

An agentic retrieval loop needs state and stop conditions. A minimal state object might record: original query, query id, first-pass sources, first-pass missing docs/chunks/terms, chosen trigger reason, reformulated query, second-pass sources, merged context policy, final missing docs/chunks/terms, and a stop reason.

That does not require a large framework on Day 16. A plain Python object/function is acceptable if it makes the decision contract explicit and testable. LangGraph vocabulary is useful because it names nodes, state, and conditional edges, but the portfolio value is the ProcureRAG evidence: the loop noticed a measured failure and tried a bounded retrieval action.

### Recursive retrieval can amplify noise and cost

A second pass is not free. It can add irrelevant chunks, duplicate documents, longer prompts, and more reranker calls. Today's artifact should record at least one no-second-pass control (for example Q001 or Q005) to prove the loop does not recursively search just because it can. It should also keep the stop condition hard: one extra pass today, no infinite loop, no hidden live-LLM dependency in the deterministic tests.

### Q092 is allowed to remain unsolved if the evidence is better

The fallback route is not failure. If Juan builds a decision/evidence contract that proves Q092 needs a different reranker strategy or alternate retrieval branch, that is valuable. The day should not fake a fix. A good Day 16 result could be: Q091 improves, Q092 remains open with a sharper diagnosis and a next targeted repair.

## Target evidence by end of day

- [ ] Boot.dev Chapter 11 lessons completed or explicitly reviewed with notes:
  - [ ] `Recursive RAG`
  - [ ] `Agentic Search`
- [ ] Companion vocabulary notes from LangChain Academy course links above, limited to what helps explain the experiment:
  - [ ] Primary: Foundation: Introduction to LangGraph - Python, Module 1 `Introduction` lessons `Motivation`, `Simple Graph`, `Router`, and `Agent`; or
  - [ ] Fallback: Quickstart: LangGraph Essentials - Python, Module 1 lessons `Nodes`, `Edges`, `Conditional Edges`, and `Memory`.
- [ ] A Juan-owned recursive retrieval artifact exists, likely `src/agentic_retrieval.py` or equivalent, reusing existing ProcureRAG retrieval/eval functions rather than bypassing them.
- [ ] The artifact has an explicit decision contract:
  - [ ] trigger reason (`missing_doc`, `missing_chunk`, `missing_term`, `low_reranker_confidence`, or a similarly precise signal);
  - [ ] reformulated query / alternate retrieval action;
  - [ ] before/after source document ids and chunk ids;
  - [ ] stop reason.
- [ ] Q091 before/after evidence records whether `POL-001::chunk-4` reaches context and whether `Band 3` remains missing.
- [ ] Q092 before/after evidence records `CONTRACT-005` and `POL-002` separately, not as one blended “missing docs” claim.
- [ ] Tests or deterministic fixtures cover at least:
  - [ ] one triggered second pass;
  - [ ] one no-second-pass control;
  - [ ] one still-open failure reported honestly.
- [ ] Verification commands are run and copied into `docs/learning-log.md`.
- [ ] `docs/eval-report.md` has a Day 16 addendum with actual evidence, or a precise blocker explaining why the experiment stopped at the contract layer.
- [ ] Juan can explain when recursive retrieval helps and when it increases noise/cost.

## Recommended 6-hour split

### Block 0 — Reactivate Week 3 evidence, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
./.venv/bin/python src/multi_doc_slice_eval.py
```

Then reread:

- `docs/learning-log.md` — Day 15 objective, full `multi_doc` slice, and `### Next step`.
- `docs/eval-report.md` — Day 15 full-slice details and Q092 root-cause diagnostic.
- `src/reranking.py` — `DEFAULT_RETRIEVAL_CONFIG`, `MULTI_DOC_RETRIEVAL_CONFIG`, `retrieval_config_for_query_type`.
- `src/regression_suite.py` — Q091's `expected_missing_terms` behavior and `--verify-retrieval` lane.
- `src/multi_doc_slice_eval.py` — per-query evidence fields to reuse or compare against.

Answer before coding:

1. What exact signal says Q091 is still incomplete?
2. Why is Q092 not just “raise top_k again”?
3. What control case proves recursive retrieval is not being applied globally?

### Block 1 — Boot.dev Chapter 11 + LangGraph vocabulary, 60–90m

Complete or review Boot.dev Chapter 11:

1. **Recursive RAG**
2. **Agentic Search**

Write brief notes in scratch form before implementation:

- What triggers another retrieval pass?
- Who decides the next query — deterministic rule, LLM, or fixed case-specific mapping for today?
- What is the maximum number of passes?
- What evidence proves the second pass helped?
- What evidence proves it did not help?

Then skim one of the LangChain Academy paths linked above:

- Preferred path: <https://academy.langchain.com/courses/intro-to-langgraph> → Module 1 `Introduction` → lessons `Motivation`, `Simple Graph`, `Router`, and `Agent`.
- Short fallback path: <https://academy.langchain.com/courses/langgraph-essentials-python> → Module 1 `Course Overview` → lessons `Nodes`, `Edges`, `Conditional Edges`, and `Memory`.

Extract vocabulary only: state, graph, node, edge, conditional edge, router, agent. Do not spend the day wiring LangGraph unless the plain recursive-retrieval contract is already clear.

### Block 2 — Design the recursive retrieval contract, 45–60m

Before writing implementation, draft the contract in `docs/eval-report.md` or local notes:

| Field | Meaning | Example for Q091 | Example for Q092 |
|---|---|---|---|
| `query_id` | Corpus query id | `Q091` | `Q092` |
| `first_pass_query` | Original buyer question | original Q091 text | original Q092 text |
| `first_pass_missing` | Missing docs/chunks/terms | `Band 3`; possibly `POL-001::chunk-4` | `CONTRACT-005`, `POL-002` |
| `trigger_reason` | Why recurse | missing term/chunk | missing docs + low/failed reranker promotion |
| `followup_query` | Targeted second query | approval band EUR thresholds | cleaning contractor onboarding insurance/vetting/security |
| `second_pass_delta` | What changed | TODO from real run | TODO from real run |
| `stop_reason` | Why stop | fixed / still missing / max passes | fixed / still missing / max passes |

Keep the first version boring and inspectable. A deterministic mapping from known failure signal to known follow-up query is acceptable for Day 16 if it teaches the control-flow lesson and leaves the next generalization honest.

### Block 3A — Primary route: Juan-owned recursive retrieval experiment, 120–150m

Possible artifact shape, for Juan to design and write:

- A small module that can run Q091/Q092 and maybe Q001/Q005 as controls.
- It should call the existing retrieval path, not duplicate indexing or load a second corpus file.
- It should compare source doc ids / chunk ids / expected terms before and after the second pass.
- It should print a compact table suitable for `docs/eval-report.md`.
- It should cap itself at one extra retrieval pass today.

Recommended behavior:

1. Run normal/current retrieval for the query.
2. Evaluate missing evidence using existing deterministic checks where possible.
3. If a trigger condition is met, build a focused follow-up query.
4. Run retrieval for the follow-up query.
5. Merge or compare the follow-up sources explicitly. If merging, state the merge rule.
6. Re-evaluate missing evidence and print the delta.

Controls:

- A clean control like Q001 should not trigger recursion.
- A multi-doc case already fine under Day 15 evidence, such as Q005, should either not trigger or should stop with “no missing evidence.”

### Block 3B — Fallback route: decision/evidence contract only, 60–90m

Use this if implementation scope gets too large.

Still produce:

1. A documented decision object / schema.
2. A test matrix with expected Q091/Q092/control behavior.
3. Manual before/after retrieval probes for the candidate follow-up queries.
4. A clear statement of what remains unimplemented.

This fallback is acceptable if it prevents an untested “agent” from landing. The portfolio story is stronger with a small honest contract than with a broad, unverified agent demo.

### Block 4 — Evidence docs + interview drill, 45–60m

Update:

- `docs/eval-report.md` — Day 16 addendum with the actual recursive retrieval table or fallback contract evidence.
- `docs/learning-log.md` — Day 16 entry with course notes, verification outputs, what improved, what stayed weak, and interview explanation.

Then answer the interview drill below without notes.

## Interview drill

1. Why did ProcureRAG move to recursive retrieval only after Week 3's gate?

   **Expected answer shape:** Because Week 3 produced deterministic evidence of specific retrieval gaps. Recursive retrieval is justified by measured missing docs/chunks/terms, not by wanting to use agents. Q091 and Q092 name the failure signals.

2. What is the difference between recursive RAG and just increasing `top_k`?

   **Expected answer shape:** Increasing `top_k` is a static retrieval-depth change. Recursive RAG is conditional control flow: inspect first-pass evidence, decide whether a targeted second query is needed, run it, and stop based on measured evidence. It can use `top_k`, but it is not the same thing.

3. Why is Q091 a good first recursive-RAG case?

   **Expected answer shape:** The document-level miss was repaired, but the exact approval-band chunk/term is still missing. That makes the follow-up query precise: retrieve approval-band EUR threshold evidence from `POL-001`, then check for `POL-001::chunk-4` / `Band 3`.

4. Why is Q092 harder than Q091?

   **Expected answer shape:** It has two missing primary docs with different owners. `CONTRACT-005` appears to be found by lexical first-stage retrieval but demoted by the reranker; `POL-002` is weaker in first-stage/fusion and still not promoted under deeper diagnostics. One generic retry may not fix both.

5. What makes an agentic retrieval loop safe enough for a learning repo?

   **Expected answer shape:** bounded passes, explicit trigger signals, deterministic tests, no-second-pass controls, stop reasons, and evidence tables that show missing docs/chunks/terms before and after. No infinite loops, no hidden live-LLM dependency in the test gate.

6. When should recursive retrieval not run?

   **Expected answer shape:** When first-pass evidence is already complete, when the query is a simple lookup/threshold case with clean controls, when the second pass has no measurable target, or when added context would increase noise/cost without a clear evidence gap.

## Hermes review protocol

When Juan has a serious Day 16 pass ready, ask Hermes:

> Day 16 recursive RAG experiment done. Review HER-283: Boot.dev Chapter 11 notes, recursive retrieval trigger contract, Q091/Q092 before/after evidence, no-second-pass control, tests, `docs/eval-report.md` Day 16 addendum, and `docs/learning-log.md` Day 16 entry. Verify pytest/compile/ruff/regression gates and do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify the evidence, and either close HER-283 or return precise remaining tasks. Hermes must not replace Juan's implementation.

## Stop condition

Day 16 is complete when:

1. Boot.dev Chapter 11 `Recursive RAG` and `Agentic Search` have been completed or reviewed and summarized.
2. The recursive retrieval loop or fallback contract is explicitly motivated by Q091/Q092 evidence.
3. Q091 and Q092 have before/after evidence at doc/chunk/term level, even if one remains open.
4. At least one no-second-pass control proves the loop is bounded and selective.
5. Tests/compile/lint and relevant eval scripts pass, or blockers are recorded honestly.
6. `docs/eval-report.md` and `docs/learning-log.md` are updated with real evidence, not imagined output.
7. Juan can explain recursive RAG as an eval-driven repair path, not framework theater.

Do not close HER-283 on route creation alone. The route is the kickoff; Juan's Chapter 11 work, implementation/contract, evidence, and interview explanation are the acceptance criteria.
